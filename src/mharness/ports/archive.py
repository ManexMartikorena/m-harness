"""Port to the archive of each session (spec hito 11, §1.5)."""

from collections.abc import Sequence
from typing import Protocol

from mharness.domain.archive import ArchiveItem, Hit, ItemLines


class ContextArchive(Protocol):
    """One session's archive. Nothing is written until something is added:
    a session that never archives leaves no file. Every method raises
    `ArchiveError` if the disk fails or the file is broken."""

    async def add(self, items: Sequence[ArchiveItem]) -> list[str]:
        """Archive the items, all or none; their ids, in their order."""
        ...

    async def search(self, query: str, limit: int) -> list[Hit]:
        """The items that best match the words of `query`, best first."""
        ...

    async def read(self, item: str, offset: int, limit: int) -> ItemLines:
        """`limit` lines of an item from line `offset` (from 1). Raises
        `ItemNotFound`."""
        ...

    async def empty(self) -> bool:
        """Whether nothing was archived."""
        ...

    async def rebuild(self, items: Sequence[ArchiveItem]) -> None:
        """Start again with only these items: the archive is an index of
        the session's file, and is made again from it."""
        ...


class ArchiveStore(Protocol):
    """The archives of every session."""

    def open(self, session_id: str) -> ContextArchive:
        """The archive of a session; nothing touches the disk yet."""
        ...

    async def move(self, old: str, new: str) -> None:
        """Give a session's archive its new id, if it has one."""
        ...

    async def delete(self, session_id: str) -> None:
        """Delete a session's archive, if it has one."""
        ...
