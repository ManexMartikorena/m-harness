"""Port to what the system prompt needs of the project and the machine
(spec hito 10, §1.4 to §1.7)."""

from typing import Protocol

from mharness.domain.prompt import Environment, Instructions


class ProjectInfo(Protocol):
    """Where `maha` runs. Read when a session's prompt is built; during a
    turn, only the instruction files of a folder the model works in
    (spec hito 11, §1.14)."""

    async def environment(self) -> Environment:
        """The working directory, its git root, the platform, the shell of
        the commands and today's date."""
        ...

    async def instructions(self) -> Instructions:
        """The user's and the project's instruction files, in their order:
        the user's, then the project's from the git root down."""
        ...

    async def nested(self, path: str) -> Instructions:
        """The project's instruction files of the folders below the working
        directory down to the one of `path`, a file a tool touched
        (absolute), from the highest: those the system prompt does not
        have (spec hito 11, §1.14). None outside the working directory."""
        ...
