"""What running a shell command gives (spec hito 5, §1.9)."""

from pydantic import BaseModel


class CommandResult(BaseModel, frozen=True):
    exit_code: int | None  # None if it was killed
    output: str  # stdout and stderr, interleaved, maybe cut
    truncated: bool
    timed_out: bool
