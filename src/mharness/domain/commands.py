"""What running a shell command gives (spec hito 5, §1.9)."""

from pydantic import BaseModel

# A runner keeps at most this much of the output: its start and its end,
# where a long `pytest` or a build says what failed (audit after hito 10,
# H4). What passes 40,000 characters goes whole to the session's archive,
# and the model sees its start, its end and its id (spec hito 11, §1.6):
# up to a million, the memory of a command stays bounded.
OUTPUT_HEAD_CHARS = 250_000
OUTPUT_TAIL_CHARS = 750_000
OUTPUT_MAX_CHARS = OUTPUT_HEAD_CHARS + OUTPUT_TAIL_CHARS


def cut_here(left_out: int) -> str:
    """The line between the start and the end of a cut output."""
    return f"\n… [output cut here: {left_out} bytes left out]\n"


class CommandResult(BaseModel, frozen=True):
    exit_code: int | None  # None if it was killed
    # stdout and stderr, interleaved; if cut, its start, `cut_here` and its
    # end.
    output: str
    truncated: bool
    timed_out: bool
    # Past the limit, it could not be killed (audit of hito 9, H4).
    still_running: bool = False
