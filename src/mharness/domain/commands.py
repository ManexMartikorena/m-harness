"""What running a shell command gives (spec hito 5, §1.9)."""

from pydantic import BaseModel

# A runner keeps at most this much of the output.
OUTPUT_MAX_CHARS = 30_000


class CommandResult(BaseModel, frozen=True):
    exit_code: int | None  # None if it was killed
    output: str  # stdout and stderr, interleaved, maybe cut
    truncated: bool
    timed_out: bool
