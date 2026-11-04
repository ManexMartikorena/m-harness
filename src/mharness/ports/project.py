"""Port to what the system prompt needs of the project and the machine
(spec hito 10, §1.4 to §1.7)."""

from typing import Protocol

from mharness.domain.prompt import Environment


class ProjectInfo(Protocol):
    """Where `maha` runs. Read when a session's prompt is built, never
    during a turn (§1.2)."""

    async def environment(self) -> Environment:
        """The working directory, its git root, the platform, the shell of
        the commands and today's date."""
        ...
