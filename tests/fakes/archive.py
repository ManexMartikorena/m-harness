"""A `ContextArchive` and an `ArchiveStore` in memory, that behave as the
SQLite ones where the application relies on it (spec hito 11, §1.5): ids by
kind, all or nothing, nothing until the first item. The search is simpler:
the items with more of the words come first."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from mharness.domain.archive import (
    ArchiveError,
    ArchiveItem,
    Hit,
    ItemLines,
    ItemNotFound,
    item_id,
    search_terms,
)


@dataclass
class MemoryArchive:
    items: dict[str, ArchiveItem] = field(default_factory=dict)
    # Set to make every call fail, as a broken file.
    broken: bool = False

    async def add(self, items: Sequence[ArchiveItem]) -> list[str]:
        self._check()
        ids = []
        added: dict[str, ArchiveItem] = {}
        for item in items:
            number = item.number
            if number is None:
                taken = [
                    int(key.split("-")[1])
                    for key, each in (self.items | added).items()
                    if each.kind == item.kind
                ]
                number = max(taken, default=0) + 1
            ids.append(item_id(item.kind, number))
            if ids[-1] not in self.items:
                added.setdefault(ids[-1], item)
        self.items.update(added)
        return ids

    async def search(self, query: str, limit: int) -> list[Hit]:
        self._check()
        terms = [term.lower() for term in search_terms(query)]
        scored = []
        for key, item in self.items.items():
            text = item.text.lower()
            score = sum(1 for term in terms if term in text)
            if score:
                scored.append((-score, key, item))
        scored.sort(key=lambda each: each[0])
        return [
            Hit(
                id=key,
                kind=item.kind,
                position=item.position,
                role=item.role,
                tool=item.tool,
                snippet=item.text[:200],
            )
            for _, key, item in scored[:limit]
        ]

    async def read(self, item: str, offset: int, limit: int) -> ItemLines:
        self._check()
        if item not in self.items:
            raise ItemNotFound(f"no archived item {item}")
        lines = self.items[item].text.split("\n")
        first = max(offset, 1)
        return ItemLines(
            id=item,
            offset=first,
            lines=lines[first - 1 : first - 1 + max(limit, 0)],
            total=len(lines),
        )

    async def empty(self) -> bool:
        self._check()
        return not self.items

    async def rebuild(self, items: Sequence[ArchiveItem]) -> None:
        self.broken = False
        self.items.clear()
        await self.add(items)

    def _check(self) -> None:
        if self.broken:
            raise ArchiveError("the archive test.db failed: file is not a database")


@dataclass
class MemoryArchiveStore:
    archives: dict[str, MemoryArchive] = field(default_factory=dict)

    def open(self, session_id: str) -> MemoryArchive:
        return self.archives.setdefault(session_id, MemoryArchive())

    async def move(self, old: str, new: str) -> None:
        if old in self.archives:
            self.archives[new] = self.archives.pop(old)

    async def delete(self, session_id: str) -> None:
        self.archives.pop(session_id, None)
