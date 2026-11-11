"""`/init`: the agent writes the project's AGENTS.md (spec hito 10, §1.9).

A normal turn whose message is `prompts/init.md`: the agent looks at the
repository with its tools and writes the file, asking first, as always.
The system prompt is fixed for the session (§1.2): a new or changed
AGENTS.md is said to take effect with the next one.
"""

from dataclasses import dataclass
from pathlib import Path

from mharness.domain.prompt import render

INSTRUCTIONS_FILE = "AGENTS.md"
TAKES_EFFECT = "[AGENTS.md takes effect in the next session: /new]"


@dataclass(frozen=True)
class Init:
    """What `/init` needs: its template, and the folder whose AGENTS.md it
    writes, where maha runs. In a subfolder of a project, `project` is the
    project's root: that folder's AGENTS.md is loaded with the root's
    (audit after hito 10, I3, decision 1 of the maintainer)."""

    template: str
    root: Path
    project: Path | None = None

    @property
    def note(self) -> str | None:
        """What the person is told in a subfolder, before the turn."""
        if self.project is None:
            return None
        return (
            f"[/init in a subfolder: it writes {self.target}, loaded with the root's]"
        )

    @property
    def target(self) -> Path:
        return self.root / INSTRUCTIONS_FILE

    def text(self, extra: str | None) -> str:
        """The turn's message; `extra`, what the person wants stressed."""
        stressed = (
            f"\n\nThe user wants this stressed:\n<user_notes>\n{extra}\n</user_notes>"
            if extra
            else ""
        )
        scope = (
            ""
            if self.project is None
            else f" this folder is part of the project at {self.project}, whose "
            "AGENTS.md is loaded with this one: write only what is specific to "
            "this folder."
        )
        return render(
            self.template, {"root": str(self.root), "scope": scope, "extra": stressed}
        )

    def stamp(self) -> tuple[int, int] | None:
        """When AGENTS.md last changed, and its size; None if it is not
        there."""
        try:
            found = self.target.stat()
        except OSError:
            return None
        return found.st_mtime_ns, found.st_size
