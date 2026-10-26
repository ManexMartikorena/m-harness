"""A `SessionStore` in memory, that behaves as the real one where the
application relies on it (spec hito 6, §1.4; final audit of hito 6, 8): the
lock, the errors, and the entries going through JSON."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import TypeAdapter

from mharness.domain.session import (
    Session,
    SessionEntry,
    SessionError,
    SessionHeader,
    SessionInUse,
    SessionNotFound,
    SessionSummary,
    is_session_id,
    replay,
    summarize,
)

_ENTRY: TypeAdapter[SessionEntry] = TypeAdapter(SessionEntry)


@dataclass
class _Stored:
    header: SessionHeader
    entries: list[SessionEntry] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class MemoryLog:
    def __init__(self, store: MemorySessionStore, session_id: str) -> None:
        self._store = store
        self._id = session_id
        self._closed = False

    async def append(self, entries: Sequence[SessionEntry]) -> None:
        if self._closed:
            raise SessionError(f"session {self._id} is closed")
        stored = self._store.sessions[self._id]
        # Through JSON, as on the disk.
        stored.entries.extend(
            _ENTRY.validate_python(
                json.loads(json.dumps(_ENTRY.dump_python(e, mode="json")))
            )
            for e in entries
        )
        stored.updated_at = datetime.now(UTC)

    async def close(self) -> None:
        # Only its own lock: closing twice frees nobody else's.
        if not self._closed:
            self._closed = True
            self._store.locked.discard(self._id)


class MemorySessionStore:
    """Sessions in `sessions`, by id; the open ones in `locked`."""

    def __init__(self) -> None:
        self.sessions: dict[str, _Stored] = {}
        self.locked: set[str] = set()

    async def create(self, header: SessionHeader) -> MemoryLog:
        if header.id in self.sessions:
            raise SessionError(f"cannot save session {header.id}: File exists")
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
