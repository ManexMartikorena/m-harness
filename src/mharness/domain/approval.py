"""What the user is asked before a tool runs, and what they answer (spec hito
5, §1.2)."""

from typing import Literal

from pydantic import BaseModel

# `once`: run this call. `session`: run it, and every later call with the same
# scope until maha ends. `deny`: do not run it.
type Decision = Literal["once", "session", "deny"]


class ApprovalRequest(BaseModel, frozen=True):
    """A question about one tool call. The tool builds it; only the tool knows
    the diff of an edit or whether a path leaves the working directory."""

    tool: str
    # One line: "edit src/app.py", "run: uv run pytest".
    title: str
    # What the user reads before deciding: the diff, the command and its
    # directory…
    detail: str
    # What "always this session" covers; None: the option is not offered.
    scope: str | None
    # "outside the working directory", "secret file"…
    warning: str | None = None
