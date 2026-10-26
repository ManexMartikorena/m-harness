"""Composition root: the only module that knows every piece.

It reads the configuration, builds the adapters, injects them into the
application and starts the `maha` command.
"""

import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from mharness import __version__, config
from mharness.adapters import cli
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
from mharness.application.agent import Agent
from mharness.application.sessions import Sessions
from mharness.application.tools import ToolRegistry
from mharness.domain.environment import command_env
from mharness.domain.messages import Message
from mharness.ports.approval import ApprovalGate


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the `maha` command."""
    options = cli.parse(argv)
    if isinstance(options, int):
        return options
    try:
        settings = config.load(cwd=Path.cwd(), env=os.environ)
    except config.ConfigError as exc:
        return cli.fail(str(exc))
    # Resolved once: the tools and the sessions name it the same way.
    return asyncio.run(_converse(settings, Path.cwd().resolve()))


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


async def _converse(settings: config.Settings, cwd: Path) -> int:
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
            return Agent(client, tools, gate=gate, model=model, history=history)

        sessions = Sessions(
            JsonlSessionStore(config.data_dir(os.environ) / "sessions"),
            new_agent,
            cwd=str(cwd),
            provider=settings.provider_name,
            model=settings.model,
            version=__version__,
        )
        return await cli.converse(
            sessions,
            provider=settings.provider_name,
            read_line=lines.readline,
            # Only a terminal has typed-ahead input to drop.
            discard=lines.discard if os.isatty(0) else None,
        )
