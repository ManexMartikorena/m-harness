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
    # "edit src/app.py", "run: uv run pytest". Shown on one line, with its
    # line breaks escaped; never cut: what you approve is seen whole (spec
    # mejora-2026-10-26-deuda-pre-hito-6, A3).
    title: str
    # What the user reads before deciding: the diff, the command and its
    # directory…
    detail: str
    # The key of what "always this session" covers; None: the option is not
    # offered.
    scope: str | None
    # That scope in words, for the person: "every edit_file in the working
    # directory" (audit after hito 10, H1).
    covers: str | None = None
    # Whether the detail is a change worth seeing also when "always" lets
    # it run without asking: the diff of an edit (audit after hito 10, P4).
    review: bool = False
    # "outside the working directory", "secret file"…
    warning: str | None = None
