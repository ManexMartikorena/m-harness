"""A `SessionStore` in memory, with the same lock as the real one (spec
hito 6, §1.4)."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from mharness.domain.session import (
    Session,
    SessionEntry,
    SessionHeader,
    SessionInUse,
    SessionNotFound,
    SessionSummary,
    is_session_id,
    replay,
    summarize,
)


@dataclass
class _Stored:
    header: SessionHeader
    entries: list[SessionEntry] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class MemoryLog:
    def __init__(self, store: MemorySessionStore, session_id: str) -> None:
        self._store = store
        self._id = session_id

    async def append(self, entries: Sequence[SessionEntry]) -> None:
        stored = self._store.sessions[self._id]
        stored.entries.extend(entries)
        stored.updated_at = datetime.now(UTC)

    async def close(self) -> None:
        self._store.locked.discard(self._id)


class MemorySessionStore:
    """Sessions in `sessions`, by id; the open ones in `locked`."""

    def __init__(self) -> None:
        self.sessions: dict[str, _Stored] = {}
        self.locked: set[str] = set()

    async def create(self, header: SessionHeader) -> MemoryLog:
        assert header.id not in self.sessions, f"session {header.id} exists"
        self.sessions[header.id] = _Stored(header)
        self.locked.add(header.id)
        return MemoryLog(self, header.id)

    async def open(self, session_id: str) -> tuple[Session, MemoryLog]:
        stored = self._get(session_id)
        session = replay(stored.header, stored.entries)
        self.locked.add(session_id)
        return session, MemoryLog(self, session_id)

    async def summaries(self) -> list[SessionSummary]:
        found = [
            summarize(stored.header, stored.entries, stored.updated_at)
            for stored in self.sessions.values()
        ]
        return sorted(found, key=lambda summary: summary.updated_at, reverse=True)

    async def delete(self, session_id: str) -> None:
        self._get(session_id)
        del self.sessions[session_id]

    def _get(self, session_id: str) -> _Stored:
        if not is_session_id(session_id) or session_id not in self.sessions:
            raise SessionNotFound(f"no session {session_id}")
        if session_id in self.locked:
            raise SessionInUse(f"session {session_id} is open in another maha")
        return self.sessions[session_id]
