"""Port to wherever sessions are kept (DESIGN §6, spec hito 6, §1.4)."""

from collections.abc import Sequence
from typing import Protocol

from mharness.domain.session import Session, SessionEntry, SessionHeader, SessionSummary


class SessionLog(Protocol):
    """An open session. The maha that holds it keeps it locked until
    `close()`: another one cannot resume it nor delete it, so two of them
    never mix their turns in one file."""

    async def append(self, entries: Sequence[SessionEntry]) -> None:
        """Add the entries at the end, all of them or none."""
        ...

    async def close(self) -> None:
        """Never fails: every append was already synced."""
        ...


class SessionStore(Protocol):
    """Creates, opens, lists and deletes sessions.

    Ids are checked with `is_session_id()` before anything else: one that
    is not raises `SessionNotFound`.
    """

    async def create(self, header: SessionHeader) -> SessionLog:
        """A new session, open and locked, with its header written."""
        ...

    async def open(self, session_id: str) -> tuple[Session, SessionLog]:
        """Read and lock in one step, so nothing changes in between. Raises
        `SessionNotFound`, `SessionInUse` or `SessionCorrupt`."""
        ...

    async def exists(self, session_id: str) -> bool:
        """Whether a session has that id, open or not. An id of another
        form has none."""
        ...

    async def summaries(self) -> list[SessionSummary]:
        """Every session, newest first. One that cannot be read is left
        out."""
        ...

    async def delete(self, session_id: str) -> None:
        """Raises `SessionNotFound` or `SessionInUse`."""
        ...
