"""Traces as JSONL files, one per session (spec hito 7, §1.7).

`<folder>/<session id>.jsonl`, one `TraceRecord` per line, only appended.
The folder is `0700` and the files `0600`, like the sessions: a trace keeps
what the tools returned. No `fsync` per record: the trace is not what a
session resumes from; `sync()` runs once per turn.

Disk calls are synchronous inside `async def`, as in the session store.
"""

import contextlib
import json
import logging
import os
from pathlib import Path

from mharness.domain.session import is_session_id
from mharness.domain.trace import TraceError, TraceExists, TraceRecord

# Read too: to see whether the file ends in a whole line.
# Diagnosis only, never content (spec hito 7, §1.11).
_log = logging.getLogger(__name__)

_OPEN = os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW


class JsonlTraceLog:
    """The open trace file of one session."""

    def __init__(self, fd: int, session: str) -> None:
        self._fd: int | None = fd
        self._session = session
        # Whether the file may end in a cut line: just opened (maha died
        # writing), or a failed write that could not be cut back.
        self._unsure = True

    async def write(self, record: TraceRecord) -> None:
        fd = self._descriptor()
        line = _line(record)
        try:
            if self._unsure:
                _end_line(fd)
                self._unsure = False
            size = os.fstat(fd).st_size
        except OSError as exc:
            raise _cannot_write(self._session, exc) from None
        try:
            _write_all(fd, line)
        except OSError as exc:
            # A half line would spoil the next one too.
            try:
                os.ftruncate(fd, size)
            except OSError:
                self._unsure = True
            raise _cannot_write(self._session, exc) from None

    async def sync(self) -> None:
        try:
            os.fsync(self._descriptor())
        except OSError as exc:
            raise _cannot_write(self._session, exc) from None

    async def close(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            # What matters was synced: a failing close loses nothing.
            with contextlib.suppress(OSError):
                os.close(fd)

    def _descriptor(self) -> int:
        if self._fd is None:
            raise TraceError(f"the trace of {self._session} is closed")
        return self._fd


class JsonlTraceSink:
    """The traces in `folder`, created with the first one."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    async def open(self, session: str, *, new: bool = False) -> JsonlTraceLog:
        path = self._path(session)
        flags = _OPEN | os.O_EXCL if new else _OPEN
        try:
            self._folder.mkdir(parents=True, exist_ok=True)
            # mkdir follows the umask: the modes are set after.
            self._folder.chmod(0o700)
        except OSError as exc:
            # Also FileExistsError, from a file where the folder goes: that
            # is not an id that is taken. The folder is named: the error
            # alone ("File exists") does not say which.
            message = (
                f"cannot write the trace of {session}: "
                f"cannot create the folder {self._folder}: {exc.strerror}"
            )
            _log.warning("%s", message)
            raise TraceError(message) from None
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            raise TraceExists(f"the trace of {session} already exists") from None
        except OSError as exc:
            raise _cannot_write(session, exc) from None
        try:
            os.fchmod(fd, 0o600)
        except OSError as exc:
            os.close(fd)
            raise _cannot_write(session, exc) from None
        return JsonlTraceLog(fd, session)

    async def read(self, session: str) -> list[TraceRecord]:
        path = self._path(session)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise TraceError(
                f"cannot read the trace of {session}: {exc.strerror}"
            ) from None
        records = []
        # The last piece has no "\n": empty, or a line cut by a crash.
        for line in data.split(b"\n")[:-1]:
            try:
                records.append(TraceRecord.model_validate(json.loads(line)))
            except ValueError, RecursionError:
                # Not JSON, not UTF-8, or not a record: skipped (§4.6.2).
                continue
        return records

    async def delete(self, session: str) -> None:
        path = self._path(session)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise TraceError(
                f"cannot delete the trace of {session}: {exc.strerror}"
            ) from None

    def location(self, session: str) -> str:
        return str(self._path(session))

    def _path(self, session: str) -> Path:
        # Checked before it becomes a file name, as with the sessions.
        if not is_session_id(session):
            raise TraceError(f"no session {session}")
        return self._folder / f"{session}.jsonl"


def _end_line(fd: int) -> None:
    """If the file ends in a cut line, end it: the next record starts on a
    line of its own, and the reader skips the broken one."""
    size = os.fstat(fd).st_size
    if size and os.pread(fd, 1, size - 1) != b"\n":
        _write_all(fd, b"\n")


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def _line(record: TraceRecord) -> bytes:
    """One JSON line, readable UTF-8; text that is not valid UTF-8 goes
    escaped (as in the session store)."""
    data = record.model_dump(mode="json")
    try:
        return (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
    except UnicodeEncodeError:
        return (json.dumps(data) + "\n").encode("ascii")


def _cannot_write(session: str, exc: OSError) -> TraceError:
    message = f"cannot write the trace of {session}: {exc.strerror}"
    # The id and the error, never what the trace holds.
    _log.warning("%s", message)
    return TraceError(message)
