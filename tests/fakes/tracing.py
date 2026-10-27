"""A `TraceSink` in memory that behaves as the real one where the
application relies on it (spec hito 7, §1.7): records through JSON, ids
checked, and writes that can be made to fail."""

from mharness.domain.session import is_session_id
from mharness.domain.trace import TraceError, TraceExists, TraceRecord


class MemoryTraceLog:
    def __init__(self, sink: MemoryTraceSink, session: str) -> None:
        self._sink = sink
        self._session = session
        self.closed = False

    async def write(self, record: TraceRecord) -> None:
        if self.closed:
            raise TraceError(f"the trace of {self._session} is closed")
        if self._sink.failures:
            self._sink.failures -= 1
            raise TraceError(
                f"cannot write the trace of {self._session}: No space left on device"
            )
        lines = self._sink.traces.setdefault(self._session, [])
        lines.append(record.model_dump_json())

    async def sync(self) -> None:
        if self.closed:
            raise TraceError(f"the trace of {self._session} is closed")
        self._sink.synced += 1

    async def close(self) -> None:
        self.closed = True


class MemoryTraceSink:
    """`traces` holds the JSON lines of each session; `failures` makes that
    many writes fail."""

    def __init__(self) -> None:
        self.traces: dict[str, list[str]] = {}
        self.failures = 0
        self.synced = 0
        self.logs: list[MemoryTraceLog] = []

    async def open(self, session: str, *, new: bool = False) -> MemoryTraceLog:
        _check(session)
        if new and session in self.traces:
            raise TraceExists(f"the trace of {session} already exists")
        # The file exists from here on, even without records.
        self.traces.setdefault(session, [])
        log = MemoryTraceLog(self, session)
        self.logs.append(log)
        return log

    async def read(self, session: str) -> list[TraceRecord]:
        _check(session)
        lines = self.traces.get(session, [])
        return [TraceRecord.model_validate_json(line) for line in lines]

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
