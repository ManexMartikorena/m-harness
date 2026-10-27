"""Composition root: the only module that knows every piece.

It reads the configuration, builds the adapters, injects them into the
application and starts the `maha` command.
"""

import asyncio
import io
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mharness import __version__, config
from mharness.adapters import cli
from mharness.adapters.catalog import CatalogError, TomlCatalog
from mharness.adapters.commands import LocalCommandRunner
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
from mharness.application.sessions import Sessions
from mharness.application.tools import ToolRegistry
from mharness.domain.environment import command_env
from mharness.domain.messages import Message
from mharness.domain.trace import known_secrets
from mharness.ports.approval import ApprovalGate
from mharness.ports.catalog import ModelCatalog


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the `maha` command."""
    options = cli.parse(argv)
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
    # Resolved once: the tools and the sessions name it the same way.
    return asyncio.run(_converse(settings, catalog, data, Path.cwd().resolve()))


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


def _gate(lines: cli.StdinLines) -> ApprovalGate:
    """Asks in the terminal; without one (`maha < notes.txt`), denies all:
    the next line of the file could "approve" (spec hito 5, §1.10)."""
    if os.isatty(0):
        return cli.TerminalApproval(
            lines.readline, sys.stdout, color=cli.use_color(), discard=lines.discard
        )
    return cli.DenyAll(sys.stdout)


async def _converse(
    settings: config.Settings, catalog: ModelCatalog, data: Path, cwd: Path
) -> int:
    provider = settings.provider
    # The variables a command gets; never the provider's key (spec
    # mejora-2026-10-23-deuda-hito-5, E1).
    drop = [provider.api_key_env] if provider.api_key_env else []
    env = command_env(os.environ, drop=drop)
    # One reader for the conversation and the questions (B3).
    lines = cli.StdinLines()
    tools = _tools(cwd, env)
    gate = _gate(lines)
    async with OpenAIChatClient(
        base_url=provider.base_url,
        api_key=settings.api_key,
        session_header=provider.session_header,
    ) as client:

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

        sessions = Sessions(
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
        return await cli.converse(
            sessions,
            provider=settings.provider_name,
            catalog=catalog,
            read_line=lines.readline,
            # Only a terminal has typed-ahead input to drop.
            discard=lines.discard if os.isatty(0) else None,
        )
