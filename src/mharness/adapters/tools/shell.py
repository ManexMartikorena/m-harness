"""`run_command`: a shell command in the working directory (spec hito 5,
§1.9).

It uses the `CommandRunner` port, never a runner adapter: adapters do not
import each other; `bootstrap` joins them. The variables the command gets
come already chosen by `domain.environment`.
"""

from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, Field

from mharness.domain.approval import ApprovalRequest
from mharness.domain.commands import CommandResult
from mharness.domain.paths import printable
from mharness.domain.tools import Permission, ToolError
from mharness.ports.commands import CommandRunner

DEFAULT_TIMEOUT = 120
# Said at the end when the runner cut the middle of the output.
CUT = "[output cut: its start and its end are kept]"


# extra="forbid" in every tool: an unknown field is an error for the
# model, not ignored (spec mejora-2026-10-26-deuda-pre-hito-6, B2).
class RunCommandParams(BaseModel, extra="forbid"):
    command: str = Field(min_length=1, description="The shell command to run")
    timeout: int = Field(
        default=DEFAULT_TIMEOUT,
        ge=1,
        le=600,
        description="Seconds before the command is killed",
    )


class RunCommand:
    name = "run_command"
    description = (
        "Run a shell command in the working directory, with a timeout. "
        "The user approves it first. It gets no input and no terminal: use "
        "options that ask nothing (git commit -m). "
        'Example: {"command": "uv run pytest -q"}'
    )
    params = RunCommandParams
    permission: Permission = "effect"
    waits_for_user = False

    def __init__(
        self, root: Path, runner: CommandRunner, env: Mapping[str, str]
    ) -> None:
        self._root = root
        self._runner = runner
        self._env = dict(env)

    async def approval(self, params: RunCommandParams) -> ApprovalRequest:
        _check_command(params.command)
        # Valid UTF-8 whatever its name (deep audit after hito 9, H7).
        lines = [f"in {printable(str(self._root))}"]
        if params.timeout != DEFAULT_TIMEOUT:
            lines.append(f"time limit: {params.timeout} s")
        # No perimeter until the sandbox (hito 15): the question says so.
        lines.append("with your permissions: it can change any file you can")
        return ApprovalRequest(
            tool=self.name,
            title=f"run: {params.command}",
            detail="\n".join(lines),
            # Only this exact command (spec hito 5, §1.3), with the time
            # limit the question shows (audit after hito 10, H6).
            scope=f"{self.name}:{params.timeout}:{params.command}",
            covers="this exact command, with this time limit",
        )

    async def run(self, params: RunCommandParams) -> str:
        _check_command(params.command)
        result = await self._runner.run(
            params.command,
            cwd=self._root,
            time_limit=params.timeout,
            env=self._env,
        )
        return _text(result, params.timeout)

    def summary(self, result: str) -> str:
        first = result.split("\n", 1)[0]
        status = "timed out" if "\n[timed out after " in result else first
        status = status.replace("exit code: ", "exit code ")
        cut = " (cut)" if f"\n{CUT}" in result else ""
        return status + cut


def _check_command(command: str) -> None:
    """What no shell can run, found before asking: a NUL ends the command
    line, and the system refuses it (audit of hito 9, H5)."""
    if "\0" in command:
        raise ToolError("the command has a NUL character")


def _text(result: CommandResult, timeout: int) -> str:
    """What the model reads. A code other than 0 is not a tool error: it is
    information for the model."""
    status = "killed" if result.exit_code is None else f"exit code: {result.exit_code}"
    text = f"{status}\n{result.output or '(no output)'}"
    notes = []
    if result.truncated:
        notes.append(CUT)
    if result.timed_out:
        notes.append(f"[timed out after {timeout} s]")
    if result.still_running:
        notes.append("[it could not be stopped: it may still be running]")
    if notes:
        text = text.removesuffix("\n") + "\n" + "\n".join(notes)
    return text
