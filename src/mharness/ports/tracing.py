"""Port to wherever traces are kept (DESIGN §6, spec hito 7, §1.7).

The records arrive already masked: the sink writes them as they are.
"""

from typing import Protocol

from mharness.domain.trace import TraceRecord


class TraceLog(Protocol):
    """The open trace of one session. Every method raises `TraceError`."""

    async def write(self, record: TraceRecord) -> None:
        """Add one record at the end. A write that fails leaves nothing
        half written."""
        ...

    async def sync(self) -> None:
        """Make what was written survive a power cut: once per turn."""
        ...

    async def close(self) -> None: ...


class TraceSink(Protocol):
    """Opens, reads and deletes the trace of each session, named by its id.

    An id of another form raises `TraceError` before anything else.
    """

    async def open(self, session: str) -> TraceLog:
        """The trace of `session`, to append to; created if new."""
        ...

    async def read(self, session: str) -> list[TraceRecord]:
        """Its records in order, skipping those that cannot be read; none
        if there is no trace."""
        ...

    async def delete(self, session: str) -> None:
        """Remove the trace; without one, nothing happens."""
        ...

    def location(self, session: str) -> str:
        """Where the trace is, for a person to open it."""
        ...
