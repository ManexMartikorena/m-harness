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
from mharness.domain.commands import OUTPUT_MAX_CHARS, CommandResult
from mharness.domain.tools import Permission
from mharness.ports.commands import CommandRunner

DEFAULT_TIMEOUT = 120


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
        'The user approves it first. Example: {"command": "uv run pytest -q"}'
    )
    params = RunCommandParams
    permission: Permission = "effect"

    def __init__(
        self, root: Path, runner: CommandRunner, env: Mapping[str, str]
    ) -> None:
        self._root = root
        self._runner = runner
        self._env = dict(env)

    async def approval(self, params: RunCommandParams) -> ApprovalRequest:
        lines = [f"in {self._root}"]
        if params.timeout != DEFAULT_TIMEOUT:
            lines.append(f"time limit: {params.timeout} s")
        # No perimeter until the sandbox (hito 15): the question says so.
        lines.append("with your permissions: it can change any file you can")
        return ApprovalRequest(
            tool=self.name,
            title=f"run: {params.command}",
            detail="\n".join(lines),
            # Only this exact command (spec hito 5, §1.3).
            scope=f"{self.name}:{params.command}",
        )

    async def run(self, params: RunCommandParams) -> str:
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
        cut = " (cut)" if "\n… [output cut at " in result else ""
        return status + cut


def _text(result: CommandResult, timeout: int) -> str:
    """What the model reads. A code other than 0 is not a tool error: it is
    information for the model."""
    status = "killed" if result.exit_code is None else f"exit code: {result.exit_code}"
    text = f"{status}\n{result.output or '(no output)'}"
    notes = []
    if result.truncated:
        notes.append(f"… [output cut at {OUTPUT_MAX_CHARS} characters]")
    if result.timed_out:
        notes.append(f"[timed out after {timeout} s]")
    if notes:
        text = text.removesuffix("\n") + "\n" + "\n".join(notes)
    return text
