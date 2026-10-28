"""Composition root: the only module that knows every piece.

It reads the configuration, builds the adapters, injects them into the
application and starts the `maha` command.
"""

import argparse
import asyncio
import io
import json
import logging
import os
import secrets
import subprocess
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mharness import __version__, config
from mharness.adapters import cli
from mharness.adapters.catalog import CatalogError, TomlCatalog
from mharness.adapters.commands import LocalCommandRunner
from mharness.adapters.evals import TomlEvalSuite
from mharness.adapters.models import OpenAIChatClient
from mharness.adapters.storage import JsonlSessionStore
from mharness.adapters.tools import (
    EditFile,
    Glob,
    Grep,
    ListDir,
    ReadFile,
    RunCommand,
    Workspace,
    WriteFile,
)
from mharness.adapters.tracing import JsonlTraceSink
from mharness.application.agent import Agent
from mharness.application.approvals import AllowList
from mharness.application.evals import Evaluator, choose
from mharness.application.sessions import Conversation, Sessions
from mharness.application.tools import ToolRegistry
from mharness.domain.environment import command_env
from mharness.domain.evals import Baseline, EvalError, Task, TaskRun, by_task, stats
from mharness.domain.messages import Message
from mharness.domain.trace import known_secrets
from mharness.ports.approval import ApprovalGate
from mharness.ports.catalog import ModelCatalog

# The tools of maha, by name: what `--allow` takes.
TOOL_NAMES = tuple(
    tool.name
    for tool in (ReadFile, ListDir, Glob, Grep, WriteFile, EditFile, RunCommand)
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the `maha` command."""
    options = cli.parse(argv, tools=TOOL_NAMES)
    if isinstance(options, int):
        return options
    try:
        _log_to(config.state_dir(os.environ) / "maha.log")
    except config.ConfigError:
        # No home: the error comes, with what to do, from load() below.
        _log_to(None)
    try:
        settings = config.load(cwd=Path.cwd(), env=os.environ)
        catalog = TomlCatalog.load(config.user_catalog_path(os.environ))
        data = config.data_dir(os.environ)
    except (config.ConfigError, CatalogError) as exc:
        return cli.fail(str(exc))
    if options.command == "eval":
        return asyncio.run(_eval(settings, catalog, options))
    # Resolved once: the tools and the sessions name it the same way.
    cwd = Path.cwd().resolve()
    if options.prompt is not None:
        return asyncio.run(_print(settings, catalog, data, cwd, options))
    return asyncio.run(_converse(settings, catalog, data, cwd))


# The application log: diagnosis for whoever maintains maha, never what was
# said (DESIGN §11, spec hito 7, §1.11). Only the adapters write to it.
_LOG_BYTES = 1024 * 1024
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class _PrivateLog(RotatingFileHandler):
    """maha.log and its rotated copy, only for the user; and quiet when it
    cannot write: Python would print the error, and the message, to the
    terminal (final review of hito 7)."""

    def _open(self) -> io.TextIOWrapper:
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        # The mode of open() follows the umask: set it after.
        os.fchmod(fd, 0o600)
        return open(fd, "a", encoding=self.encoding, errors=self.errors)

    def handleError(self, record: logging.LogRecord) -> None:
        pass


def _log_to(path: Path | None) -> None:
    """Send the warnings of `mharness.*` to `path`, rotated at 1 MiB with one
    copy. Without a place for it, nowhere: never to the terminal."""
    logger = logging.getLogger("mharness")
    logger.setLevel(logging.WARNING)
    # Not to the root's handlers, nor twice if main() runs again.
    logger.propagate = False
    for old in list(logger.handlers):
        logger.removeHandler(old)
        old.close()
    handler: logging.Handler = logging.NullHandler()
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # mkdir follows the umask: the mode is set after.
            path.parent.chmod(0o700)
            handler = _PrivateLog(
                path, maxBytes=_LOG_BYTES, backupCount=1, encoding="utf-8"
            )
        except OSError:
            pass
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(handler)


def _tools(cwd: Path, env: Mapping[str, str]) -> ToolRegistry:
    """The seven tools, over the directory where `maha` started."""
    workspace = Workspace(cwd)
    return ToolRegistry(
        [
            ReadFile(workspace),
            ListDir(workspace),
            Glob(workspace),
            Grep(workspace),
            WriteFile(workspace),
            EditFile(workspace),
            RunCommand(workspace.root, LocalCommandRunner(), env),
        ]
    )


def _eval_tools(cwd: Path) -> ToolRegistry:
    """The tools of an eval run: all but `run_command`, until the sandbox
    of hito 15 (spec hito 8, decision 2)."""
    workspace = Workspace(cwd)
    return ToolRegistry(
        [
            ReadFile(workspace),
            ListDir(workspace),
            Glob(workspace),
            Grep(workspace),
            WriteFile(workspace),
            EditFile(workspace),
        ]
    )


async def _eval(
    settings: config.Settings, catalog: ModelCatalog, options: argparse.Namespace
) -> int:
    """`maha eval` (spec hito 8, §1.5 to §1.9)."""
    if options.save and (options.split != "all" or options.only):
        return cli.fail(
            "--save keeps a baseline of the whole battery: drop --split and --only"
        )
    suite = TomlEvalSuite(Path(options.tasks), keep=options.keep)
    try:
        tasks = choose(await suite.tasks(), options.split, options.only)
        models: list[str] = options.models or [settings.model]
        baselines = {
            model: await suite.baseline(settings.provider_name, model)
            for model in models
        }
    except EvalError as exc:
        return cli.fail(str(exc))
    provider = settings.provider
    drop = [provider.api_key_env] if provider.api_key_env else []
    env = command_env(os.environ, drop=drop)
    masked = known_secrets(os.environ, also=[settings.api_key])
    # Each run's sessions and traces, apart from the user's; the suffix
    # keeps two `maha eval` of the same second apart.
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    run_dir = config.state_dir(os.environ) / "evals" / stamp

    @asynccontextmanager
    async def open_run(
        task: Task, model: str, cwd: Path
    ) -> AsyncIterator[Conversation]:
        # A client per run: each one is a session of its own for the
        # provider, as a `maha -p` would be.
        async with _client(settings) as client:
            tools = _eval_tools(cwd)

            def new_agent(model: str, history: Sequence[Message]) -> Agent:
                return Agent(
                    client,
                    tools,
                    gate=AllowList(task.allow),
                    model=model,
                    catalog=catalog,
                    provider=settings.provider_name,
                    limits=task.limits,
                    history=history,
                )

            sessions = Sessions(
                JsonlSessionStore(run_dir / "sessions"),
                new_agent,
                cwd=str(cwd),
                provider=settings.provider_name,
                model=model,
                version=__version__,
                traces=JsonlTraceSink(run_dir / "traces"),
                masked=masked,
            )
            conversation = await sessions.start()
            try:
                yield conversation
            finally:
                await conversation.close()

    print(
        f"evals: {len(tasks)} tasks · {', '.join(models)} · "
        f"{options.repeat} run{'' if options.repeat == 1 else 's'} each · "
        f"{options.jobs} at once",
        flush=True,
    )
    evaluator = Evaluator(suite, open_run, LocalCommandRunner(), env)
    runs = await evaluator.run(
        tasks,
        models,
        repeat=options.repeat,
        jobs=options.jobs,
        retry_errors=options.retry_errors,
        on_run=lambda run: print(cli.run_line(run), flush=True),
    )
    regressed = cli.eval_report(runs, baselines, sys.stdout)
    # Every run in full: the report shows one line of a failure.
    await asyncio.to_thread(_write_runs, run_dir / "runs.json", runs)
    if options.save:
        commit = _commit()
        for model in models:
            mine = [run for run in runs if run.model == model]
            where = await suite.save(
                Baseline(
                    date=datetime.now().date(),
                    maha=__version__,
                    commit=commit,
                    provider=settings.provider_name,
                    model=model,
                    repeat=options.repeat,
                    tasks=by_task(mine),
                    total=stats(mine),
                )
            )
            print(f"\nsaved: {where}")
    print(f"\nsessions and traces of these runs: {run_dir}")
    return 1 if regressed else 0


def _write_runs(path: Path, runs: Sequence[TaskRun]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps([run.model_dump(mode="json") for run in runs], indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def _commit() -> str | None:
    """The commit the battery measured, `-dirty` if the tree had changes;
    None outside a repository."""
    try:
        done = subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return done.stdout.strip() or None


def _gate(lines: cli.StdinLines) -> ApprovalGate:
    """Asks in the terminal; without one (`maha < notes.txt`), denies all:
    the next line of the file could "approve" (spec hito 5, §1.10)."""
    if os.isatty(0):
        return cli.TerminalApproval(
            lines.readline, sys.stdout, color=cli.use_color(), discard=lines.discard
        )
    return cli.DenyAll(sys.stdout)


def _sessions(
    settings: config.Settings,
    catalog: ModelCatalog,
    data: Path,
    cwd: Path,
    client: OpenAIChatClient,
    gate: ApprovalGate,
) -> Sessions:
    """The user's sessions, whose agents have the seven tools and `gate`."""
    provider = settings.provider
    # The variables a command gets; never the provider's key (spec
    # mejora-2026-10-23-deuda-hito-5, E1).
    drop = [provider.api_key_env] if provider.api_key_env else []
    tools = _tools(cwd, command_env(os.environ, drop=drop))

    def new_agent(model: str, history: Sequence[Message]) -> Agent:
        return Agent(
            client,
            tools,
            gate=gate,
            model=model,
            catalog=catalog,
            provider=settings.provider_name,
            limits=settings.limits,
            history=history,
        )

    return Sessions(
        JsonlSessionStore(data / "sessions"),
        new_agent,
        cwd=str(cwd),
        provider=settings.provider_name,
        model=settings.model,
        version=__version__,
        traces=JsonlTraceSink(data / "traces"),
        # The provider's key and every variable that looks like one never
        # reach a trace (spec hito 7, §1.8).
        masked=known_secrets(os.environ, also=[settings.api_key]),
    )


def _client(settings: config.Settings) -> OpenAIChatClient:
    provider = settings.provider
    return OpenAIChatClient(
        base_url=provider.base_url,
        api_key=settings.api_key,
        session_header=provider.session_header,
    )


async def _print(
    settings: config.Settings,
    catalog: ModelCatalog,
    data: Path,
    cwd: Path,
    options: argparse.Namespace,
) -> int:
    """`maha -p` (spec hito 8, §1.10 and §1.11). Nobody to ask: only the
    tools of `--allow` run, and only with a scope (§1.2)."""
    # From a terminal nothing is piped: -p does not wait for Ctrl+D.
    read_all = None if os.isatty(0) else cli.StdinLines().read_all
    async with _client(settings) as client:
        sessions = _sessions(
            settings, catalog, data, cwd, client, AllowList(options.allow)
        )
        return await cli.print_mode(
            sessions,
            options.prompt,
            read_all=read_all,
            catalog=catalog,
            provider=settings.provider_name,
            output_format=options.output_format,
        )


async def _converse(
    settings: config.Settings, catalog: ModelCatalog, data: Path, cwd: Path
) -> int:
    # One reader for the conversation and the questions (B3).
    lines = cli.StdinLines()
    async with _client(settings) as client:
        sessions = _sessions(settings, catalog, data, cwd, client, _gate(lines))
        return await cli.converse(
            sessions,
            provider=settings.provider_name,
            catalog=catalog,
            read_line=lines.readline,
            # Only a terminal has typed-ahead input to drop.
            discard=lines.discard if os.isatty(0) else None,
        )
