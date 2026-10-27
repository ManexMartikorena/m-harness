"""A `TraceSink` in memory that behaves as the real one where the
application relies on it (spec hito 7, §1.7; audit of hito 7): records
through JSON, ids checked, broken lines skipped when read, writes to a
deleted trace lost, and every operation able to fail on demand."""

from pydantic import ValidationError

from mharness.domain.session import is_session_id
from mharness.domain.trace import TraceError, TraceExists, TraceRecord


class MemoryTraceLog:
    def __init__(self, sink: MemoryTraceSink, session: str, lines: list[str]) -> None:
        self._sink = sink
        self._session = session
        # The trace's own lines: once deleted, writes go nowhere, as with an
        # unlinked file.
        self._lines = lines
        self.closed = False

    async def write(self, record: TraceRecord) -> None:
        self._check()
        if self._sink.failures:
            self._sink.failures -= 1
            raise TraceError(
                f"cannot write the trace of {self._session}: No space left on device"
            )
        self._lines.append(record.model_dump_json())

    async def sync(self) -> None:
        self._check()
        if self._sink.sync_failures:
            self._sink.sync_failures -= 1
            raise TraceError(
                f"cannot write the trace of {self._session}: Input/output error"
            )
        self._sink.synced += 1

    async def close(self) -> None:
        self.closed = True

    def _check(self) -> None:
        if self.closed:
            raise TraceError(f"the trace of {self._session} is closed")


class MemoryTraceSink:
    """`traces` holds the JSON lines of each session. `failures`,
    `open_failures`, `sync_failures` and `read_failures` make that many
    writes, opens, syncs and reads fail."""

    def __init__(self) -> None:
        self.traces: dict[str, list[str]] = {}
        self.failures = 0
        self.open_failures = 0
        self.sync_failures = 0
        self.read_failures = 0
        self.synced = 0
        self.logs: list[MemoryTraceLog] = []

    async def open(self, session: str, *, new: bool = False) -> MemoryTraceLog:
        _check(session)
        if new and session in self.traces:
            raise TraceExists(f"the trace of {session} already exists")
        if self.open_failures:
            self.open_failures -= 1
            raise TraceError(f"cannot write the trace of {session}: Permission denied")
        # The file exists from here on, even without records.
        lines = self.traces.setdefault(session, [])
        log = MemoryTraceLog(self, session, lines)
        self.logs.append(log)
        return log

    async def read(self, session: str) -> list[TraceRecord]:
        _check(session)
        if self.read_failures:
            self.read_failures -= 1
            raise TraceError(f"cannot read the trace of {session}: Input/output error")
        records = []
        for line in self.traces.get(session, []):
            try:
                records.append(TraceRecord.model_validate_json(line))
            except ValidationError:
                continue
        return records

    async def delete(self, session: str) -> None:
        _check(session)
        self.traces.pop(session, None)

    def location(self, session: str) -> str:
        _check(session)
        return f"/traces/{session}.jsonl"

    def events(self, session: str) -> list[str]:
        """The `type` of each record, for short assertions."""
        return [
            TraceRecord.model_validate_json(line).event.type
            for line in self.traces.get(session, [])
        ]


def _check(session: str) -> None:
    if not is_session_id(session):
        raise TraceError(f"no session {session}")
