"""Port to whatever runs a shell command (DESIGN §6, spec hito 5, §1.9)."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from mharness.domain.commands import CommandResult


class CommandRunner(Protocol):
    """Runs one command in `cwd`, with exactly the variables of `env`, and
    kills it after `time_limit` seconds or when the task is cancelled.

    `time_limit`, not `timeout`: the runner itself stops the command and
    keeps what it wrote; a timeout around the call would cancel it and lose
    that output.

    `env` comes already filtered (spec mejora-2026-10-23-deuda-hito-5, B4):
    which variables a command gets is not the runner's decision.
    """

    async def run(
        self, command: str, *, cwd: Path, time_limit: float, env: Mapping[str, str]
    ) -> CommandResult: ...
