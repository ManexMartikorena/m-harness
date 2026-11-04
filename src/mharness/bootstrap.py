"""Composition root: the only module that knows every piece.

It reads the configuration, builds the adapters, injects them into the
application and starts the `maha` command.
"""

import argparse
import asyncio
import contextlib
import io
import json
import logging
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime
from importlib import resources
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

from mharness import __version__, config
from mharness.adapters import cli
from mharness.adapters.catalog import CatalogError, TomlCatalog
from mharness.adapters.commands import LocalCommandRunner
from mharness.adapters.evals import TomlEvalSuite
from mharness.adapters.models import AnthropicClient, OpenAIChatClient
from mharness.adapters.project import LocalProject
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
from mharness.application.prompt import PromptTemplates, SystemPromptBuilder
from mharness.application.routing import ModelRouter
from mharness.application.sessions import Conversation, Sessions, Start
from mharness.application.tools import ToolRegistry
from mharness.domain.environment import command_env
from mharness.domain.evals import (
    BASELINE_REPEAT,
    Baseline,
    EvalError,
    Task,
    TaskRun,
    by_task,
    stats,
)
from mharness.domain.limits import TurnLimits
from mharness.domain.messages import Message
from mharness.domain.prompt import Layer, sections
from mharness.domain.trace import known_secrets
from mharness.ports.approval import ApprovalGate
from mharness.ports.catalog import ModelCatalog
from mharness.ports.model import ModelClient

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
        # Only what calls the model needs a model and the key.
        settings = config.load(
            cwd=Path.cwd(),
            env=os.environ,
            calls_model=options.command in _CALL_THE_MODEL,
        )
        catalog = TomlCatalog.load(config.user_catalog_path(os.environ))
        data = config.data_dir(os.environ)
    except (config.ConfigError, CatalogError) as exc:
        json_result = options.prompt is not None and options.output_format != "text"
        return cli.fail(str(exc), result=json_result)
    try:
        code = _dispatch(options, settings, catalog, data)
        # Inside: Python's own last flush would print "Exception ignored".
        sys.stdout.flush()
    except BrokenPipeError:
        # Nobody reads stdout any more (`maha export ID | head -1`): quiet,
        # as `maha -p` (audit of hito 8).
        cli.drop_output(sys.stdout)
        return 1
    return code


def _dispatch(
    options: argparse.Namespace,
    settings: config.Settings,
    catalog: ModelCatalog,
    data: Path,
) -> int:
    """Run the command the line asks for; return its exit code."""
    if options.command == "eval":
        try:
            return asyncio.run(_eval(settings, catalog, options))
        except KeyboardInterrupt:
            # What finished is already in its runs.json (`_eval`).
            return 130
    if options.command == "models":
        cli.models_report(
            catalog.models(),
            settings.provider_name,
            every=options.every,
            out=sys.stdout,
            # The format of the built-in providers' models, and the user's.
            apis={
                **{name: p.api for name, p in config.BUILTIN_PROVIDERS.items()},
                settings.provider_name: settings.provider.api,
            },
        )
        return 0
    if options.command == "stats":
        return asyncio.run(
            cli.show_stats(
                JsonlTraceSink(data / "traces"),
                days=options.days,
                today=date.today(),
                out=sys.stdout,
                err=sys.stderr,
            )
        )
    if options.command in ("sessions", "trace", "export", "import"):
        return asyncio.run(_sessions_command(settings, catalog, data, options))
    try:
        files = _prompt_files(settings, options)
    except config.ConfigError as exc:
        json_result = options.prompt is not None and options.output_format != "text"
        return cli.fail(str(exc), result=json_result)
    # Resolved once: the tools and the sessions name it the same way.
    cwd = Path.cwd().resolve()
    if options.command == "prompt":
        model = options.model or settings.model
        return asyncio.run(_show_prompt(settings, catalog, cwd, files, model))
    settings = _with_options(settings, options)
    start = Start(last=options.last, session=options.session, model=options.model)
    if options.prompt is not None:
        return asyncio.run(_print(settings, catalog, data, cwd, start, options, files))
    return asyncio.run(_converse(settings, catalog, data, cwd, start, files))


@dataclass(frozen=True)
class _PromptFiles:
    """What the command line and the user's configuration put in the system
    prompt: their own base, and what goes at the end (spec hito 10, §1.8)."""

    base: Layer | None = None
    append: tuple[Layer, ...] = ()


def _prompt_files(
    settings: config.Settings, options: argparse.Namespace
) -> _PromptFiles:
    """Read the files of the options; a `ConfigError` says which and why.
    The base of the command line wins over the configuration's."""
    path: Path | None = options.system_prompt_file or settings.system_prompt_file
    base = None
    if path is not None:
        base = Layer(kind="base", source=str(path), text=_read_prompt(path))
    append: list[Layer] = []
    if options.append_system_prompt_file is not None:
        path = options.append_system_prompt_file
        append.append(Layer(kind="append", source=str(path), text=_read_prompt(path)))
    if options.append_system_prompt is not None:
        append.append(
            Layer(
                kind="append",
                source="--append-system-prompt",
                text=options.append_system_prompt,
            )
        )
    return _PromptFiles(base, tuple(append))


def _read_prompt(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        raise config.ConfigError(f"{path}: not UTF-8") from None
    except OSError as exc:
        raise config.ConfigError(f"{path}: cannot read it: {exc.strerror}") from None
    if not text:
        raise config.ConfigError(f"{path}: empty")
    return text


async def _show_prompt(
    settings: config.Settings,
    catalog: ModelCatalog,
    cwd: Path,
    files: _PromptFiles,
    model: str | None,
) -> int:
    """`maha prompt`: the system prompt of a session here, with the tools
    of a conversation, without calling the model (spec hito 10, §1.8)."""
    tools = _tools(cwd, {})
    prompt = await _prompt(settings, catalog, cwd, tools, files).build(model or "")
    for note in cli.prompt_notes(prompt):
        print(f"  {note}", file=sys.stderr)
    print(prompt.text)
    return 0


# The conversation, `-p` (both without a command) and the evals.
_CALL_THE_MODEL = (None, "eval")

# The limits of the turn the command line can set (spec hito 8, §1.13).
_LIMITS = ("max_steps", "max_cost", "max_tokens", "timeout")


def _with_options(
    settings: config.Settings, options: argparse.Namespace
) -> config.Settings:
    """The limits and the fallback model of the command line win over the
    configuration's: they are what the user asked for this run."""
    given = {
        name: getattr(options, name)
        for name in _LIMITS
        if getattr(options, name) is not None
    }
    limits = TurnLimits.model_validate(settings.limits.model_dump() | given)
    fallback = options.fallback_model or settings.fallback_model
    effort = options.effort or settings.effort
    return settings.model_copy(
        update={"limits": limits, "fallback_model": fallback, "effort": effort}
    )


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


# The shell `run_command` runs in: asyncio's subprocess shell.
COMMAND_SHELL = "/bin/sh"


def _templates() -> PromptTemplates:
    """The prompt templates of the package (spec hito 10, §1.3)."""
    root = resources.files("mharness") / "prompts"
    families = root / "families"
    return PromptTemplates(
        base=(root / "base.md").read_text(encoding="utf-8"),
        tools=sections((root / "tools.md").read_text(encoding="utf-8")),
        families={
            entry.name.removesuffix(".md"): entry.read_text(encoding="utf-8").strip()
            for entry in (families.iterdir() if families.is_dir() else ())
            if entry.name.endswith(".md")
        },
    )


def _prompt(
    settings: config.Settings,
    catalog: ModelCatalog,
    cwd: Path,
    tools: ToolRegistry,
    files: _PromptFiles | None = None,
) -> SystemPromptBuilder:
    """The system prompt of the user's sessions (spec hito 10)."""
    project = LocalProject(
        cwd,
        shell=COMMAND_SHELL if tools.get("run_command") is not None else None,
        home=config.home(),
        config_dir=config.config_dir(os.environ),
        compat_claude=settings.compat_claude,
        extra_user=settings.instructions,
        extra_project=settings.project_instructions,
    )
    files = files or _PromptFiles()
    return SystemPromptBuilder(
        project,
        _templates(),
        catalog=catalog,
        provider=settings.provider_name,
        tools=tools.names(),
        base=files.base,
        append=files.append,
    )


def _eval_prompt(
    settings: config.Settings, catalog: ModelCatalog, cwd: Path, tools: ToolRegistry
) -> SystemPromptBuilder:
    """The system prompt of an eval run: only the task's own files, never
    the user's instructions nor those of the directory maha eval runs in
    (spec hito 10, §5)."""
    project = LocalProject(
        cwd,
        shell=None,
        home=config.home(),
        config_dir=config.config_dir(os.environ),
        user=False,
    )
    return SystemPromptBuilder(
        project,
        _templates(),
        catalog=catalog,
        provider=settings.provider_name,
        tools=tools.names(),
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
    effort = options.eval_effort or settings.effort
    if options.save and effort is not None:
        # A baseline does not say its effort, and the next runs compare
        # against it (spec hito 9, §5).
        return cli.fail(
            "--save keeps a baseline with the model's own effort: drop --effort "
            "and the effort of the configuration"
        )
    if options.save and options.repeat < BASELINE_REPEAT:
        # One pass is noise (spec hito 8, decision 3; deep audit, I13).
        return cli.fail(
            f"--save keeps a baseline of {BASELINE_REPEAT} runs of each task or "
            f"more: add --repeat {BASELINE_REPEAT}"
        )
    # load() requires a model for the evals.
    assert settings.model is not None
    # Each run's sessions and traces, apart from the user's; the suffix
    # keeps two `maha eval` of the same second apart.
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    run_dir = config.state_dir(os.environ) / "evals" / stamp
    # With --keep, the copies of this battery, together and said at the end
    # (deep audit, I9).
    copies = Path(tempfile.gettempdir()) / f"maha-eval-{stamp}"
    suite = TomlEvalSuite(Path(options.tasks), keep=copies if options.keep else None)
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

    @asynccontextmanager
    async def open_run(
        task: Task, model: str, cwd: Path
    ) -> AsyncIterator[Conversation]:
        # A client per run: each one is a session of its own for the
        # provider, as a `maha -p` would be.
        async with _client(settings, catalog) as client:
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
                    # Retries, but no fallback: an eval measures the model
                    # it names.
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
                effort=effort,
                prompt=_eval_prompt(settings, catalog, cwd, tools),
            )
            conversation = await sessions.start()
            try:
                yield conversation
            finally:
                await conversation.close()

    out = _Out()
    head = (
        f"evals: {len(tasks)} tasks · {', '.join(models)} · "
        f"{options.repeat} run{'' if options.repeat == 1 else 's'} each · "
        f"{options.jobs} at once" + (f" · effort {effort}" if effort else "")
    )
    out.line(head)
    evaluator = Evaluator(suite, open_run, LocalCommandRunner(), env)

    def on_run(run: TaskRun) -> None:
        out.line(cli.run_line(run))

    # Closing the window or `kill` end the battery as Ctrl+C does: what
    # finished is kept, the copies go, and the code is 128 + the signal
    # (deep audit, I6). Ctrl+C is asyncio.run's own.
    loop = asyncio.get_running_loop()
    current = asyncio.current_task()
    assert current is not None
    received: list[int] = []

    def on_signal(number: int) -> None:
        received.append(number)
        # Only the first: another one while what finished is written would
        # cut the writing, and end in a traceback (review of the deep audit).
        if len(received) == 1:
            current.cancel()

    for number in _CLOSING:
        loop.add_signal_handler(number, on_signal, number)
    try:
        runs = await evaluator.run(
            tasks,
            models,
            repeat=options.repeat,
            jobs=options.jobs,
            retry_errors=options.retry_errors,
            on_run=on_run,
        )
    except asyncio.CancelledError:
        # What ended, with its paid calls (audit of hito 8).
        done = evaluator.finished
        await asyncio.to_thread(_write_runs, run_dir / "runs.json", done)
        kept = f"{len(done)} run" + ("" if len(done) == 1 else "s")
        # A closed window may have taken the terminal: runs.json is written.
        with contextlib.suppress(OSError):
            print(f"\ninterrupted: {kept} kept in {run_dir}", file=sys.stderr)
            if options.keep:
                print(f"copies of the repositories: {copies}", file=sys.stderr)
            sys.stderr.flush()
        if not received:
            raise
        current.uncancel()
        return 128 + received[0]
    finally:
        for number in _CLOSING:
            loop.remove_signal_handler(number)
    # Every run in full, first: the report shows one line of a failure, and
    # may find nobody reading (deep audit, I6).
    await asyncio.to_thread(_write_runs, run_dir / "runs.json", runs)
    # The base prompt of each model, as its runs had it (spec hito 10, §1.13).
    here = Path.cwd()
    builder = _eval_prompt(settings, catalog, here, _eval_tools(here))
    prompts = {model: builder.base_fingerprint(model) for model in models}
    regressed = out.show(
        lambda stream: cli.eval_report(
            runs, baselines, stream, effort=effort, prompts=prompts
        )
    )
    broken = {
        model: count
        for model in models
        if (count := sum(r.model == model and r.outcome == "error" for r in runs))
    }
    if options.save and broken:
        # A baseline without the runs that did not finish would not be the
        # battery's (deep audit, I13).
        for model, count in broken.items():
            cli.fail(
                f"not saved: {count} run{'' if count == 1 else 's'} of {model} "
                "ended in an error; run the battery again (--retry-errors) to "
                "keep a baseline"
            )
        out.line(f"\nsessions and traces of these runs: {run_dir}")
        return 1
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
                    prompt=prompts[model],
                )
            )
            out.line(f"\nsaved: {where}")
    out.line(f"\nsessions and traces of these runs: {run_dir}")
    if options.keep:
        out.line(f"copies of the repositories: {copies}")
    return 1 if regressed else 0


# Closing the window (SIGHUP) and `kill` (SIGTERM).
_CLOSING = (signal.SIGHUP, signal.SIGTERM)


class _Out:
    """The stdout of `maha eval` until nobody reads it (`maha eval | head`);
    then nothing more is shown, and the battery goes on: runs.json keeps
    every run (deep audit, I6)."""

    def __init__(self) -> None:
        self._stream: TextIO = sys.stdout

    def show[T](self, write: Callable[[TextIO], T]) -> T:
        """Run `write` on the stream, and return what it returns."""
        try:
            done = write(self._stream)
            self._stream.flush()
        except BrokenPipeError:
            cli.drop_output(sys.stdout)
            # Somewhere to write that nobody reads: the report still has to
            # say whether there was a regression.
            self._stream = io.StringIO()
            done = write(self._stream)
        return done

    def line(self, text: str) -> None:
        self.show(lambda stream: print(text, file=stream))


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


def _notes(settings: config.Settings) -> list[str]:
    """What to say at start: what the project's file chose (deep audit
    after hito 9, M4)."""
    note = cli.project_note(settings.from_project)
    return [] if note is None else [note]


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
    client: ModelClient,
    gate: ApprovalGate,
    files: _PromptFiles | None = None,
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
            # Retries with the default policy (spec hito 8, §1.14).
            fallback=settings.fallback_model,
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
        effort=settings.effort,
        prompt=_prompt(settings, catalog, cwd, tools, files),
    )


async def _sessions_command(
    settings: config.Settings,
    catalog: ModelCatalog,
    data: Path,
    options: argparse.Namespace,
) -> int:
    """`maha sessions`, `trace`, `export`, `import` and what they take
    (spec hito 8, §1.15). No call to the model: the client is there
    because a conversation needs one."""
    cwd = Path.cwd().resolve()
    async with _client(settings, catalog) as client:
        sessions = _sessions(
            settings, catalog, data, cwd, client, cli.DenyAll(sys.stdout)
        )
        if options.command == "export":
            return await cli.export_session(
                sessions,
                options.id,
                output_format=options.export_format,
                out=sys.stdout,
                err=sys.stderr,
            )
        if options.command == "import":
            return await cli.import_session(
                sessions, options.file, out=sys.stdout, err=sys.stderr
            )
        if options.command == "trace":
            return await cli.show_trace(
                sessions, options.id, out=sys.stdout, err=sys.stderr, home=Path.home()
            )
        if options.action == "delete":
            return await cli.delete_session(
                sessions, options.id, out=sys.stdout, err=sys.stderr
            )
        return await cli.list_sessions(sessions, out=sys.stdout, home=Path.home())


@asynccontextmanager
async def _client(
    settings: config.Settings, catalog: ModelCatalog
) -> AsyncIterator[ModelClient]:
    """A client for each API format the provider serves, behind a router
    that picks the one of each request's model (spec hito 9, §1.2)."""
    provider = settings.provider
    # One id for the provider's session, whatever the format.
    session = str(uuid.uuid4())
    async with AsyncExitStack() as stack:
        clients: dict[str, ModelClient] = {}
        if (url := provider.url("openai-chat")) is not None:
            clients["openai-chat"] = await stack.enter_async_context(
                OpenAIChatClient(
                    base_url=url,
                    api_key=settings.api_key,
                    session_header=provider.session_header,
                    session_id=session,
                )
            )
        if (url := provider.url("anthropic")) is not None:
            clients["anthropic"] = await stack.enter_async_context(
                AnthropicClient(
                    base_url=url,
                    api_key=settings.api_key,
                    session_header=provider.session_header,
                    session_id=session,
                    version=provider.anthropic_version,
                    cache_ttl=settings.cache_ttl,
                )
            )

        def api_of(model: str) -> str:
            info = catalog.get(settings.provider_name, model)
            return info.api if info is not None and info.api else provider.api

        yield ModelRouter(clients, api_of)


async def _print(
    settings: config.Settings,
    catalog: ModelCatalog,
    data: Path,
    cwd: Path,
    start: Start,
    options: argparse.Namespace,
    files: _PromptFiles,
) -> int:
    """`maha -p` (spec hito 8, §1.10 and §1.11). Nobody to ask: only the
    tools of `--allow` run, and only with a scope (§1.2)."""
    # From a terminal nothing is piped: -p does not wait for Ctrl+D.
    read_all = None if os.isatty(0) else cli.StdinLines().read_all
    async with _client(settings, catalog) as client:
        sessions = _sessions(
            settings, catalog, data, cwd, client, AllowList(options.allow), files
        )
        return await cli.print_mode(
            sessions,
            options.prompt,
            read_all=read_all,
            catalog=catalog,
            provider=settings.provider_name,
            output_format=options.output_format,
            start=start,
            notes=_notes(settings),
        )


async def _converse(
    settings: config.Settings,
    catalog: ModelCatalog,
    data: Path,
    cwd: Path,
    start: Start,
    files: _PromptFiles,
) -> int:
    # One reader for the conversation and the questions (B3).
    lines = cli.StdinLines()
    async with _client(settings, catalog) as client:
        sessions = _sessions(settings, catalog, data, cwd, client, _gate(lines), files)
        return await cli.converse(
            sessions,
            provider=settings.provider_name,
            catalog=catalog,
            read_line=lines.readline,
            # Only a terminal has typed-ahead input to drop.
            discard=lines.discard if os.isatty(0) else None,
            start=start,
            notes=_notes(settings),
        )
