"""Sessions as JSONL files, one per session (spec hito 6, §1.3 and §1.5).

`<folder>/<id>.jsonl`: a header line, then one `SessionEntry` per line.
Lines are only appended; a turn is one write followed by `fsync`. The folder
is `0700` and the files `0600`: a session keeps all the agent read.

Disk calls are synchronous inside `async def`, as in the file tools: small
writes, and no threads (spec hito 2, §12).
"""

import fcntl
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from mharness.domain.session import (
    Session,
    SessionCorrupt,
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

VERSION = 1
_ENTRY: TypeAdapter[SessionEntry] = TypeAdapter(SessionEntry)


class JsonlLog:
    """An open session file."""

    def __init__(self, fd: int, path: Path) -> None:
        self._fd: int | None = fd
        self._path = path

    async def append(self, entries: Sequence[SessionEntry]) -> None:
        data = "".join(_ENTRY.dump_json(entry).decode() + "\n" for entry in entries)
        _write(self._descriptor(), self._path, data.encode())

    async def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _descriptor(self) -> int:
        if self._fd is None:
            raise SessionError(f"session {self._path.stem} is closed")
        return self._fd


class JsonlSessionStore:
    """The sessions in `folder`, created when the first one is."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    async def create(self, header: SessionHeader) -> JsonlLog:
        path = self._path(header.id)
        try:
            self._folder.mkdir(parents=True, exist_ok=True)
            # mkdir follows the umask: the mode is set after.
            self._folder.chmod(0o700)
            fd = os.open(path, _CREATE, 0o600)
        except OSError as exc:
            raise _cannot_save(path, exc) from None
        log = JsonlLog(fd, path)
        try:
            _lock(fd, header.id)
            os.fchmod(fd, 0o600)
            line = {
                "type": "session",
                "version": VERSION,
                **header.model_dump(mode="json"),
            }
            _write(fd, path, (json.dumps(line, ensure_ascii=False) + "\n").encode())
            # The new name survives a power cut too.
            _sync_folder(self._folder)
        except BaseException:
            await log.close()
            raise
        return log

    async def open(self, session_id: str) -> tuple[Session, JsonlLog]:
        path = self._path(session_id)
        try:
            fd = os.open(path, _OPEN)
        except FileNotFoundError:
            raise _not_found(session_id) from None
        except OSError as exc:
            raise SessionError(
                f"cannot open session {session_id}: {exc.strerror}"
            ) from None
        log = JsonlLog(fd, path)
        try:
            _lock(fd, session_id)
            if not _still_named(fd, path):
                raise _not_found(session_id)
            data = _read(fd)
            whole = _whole_lines(data)
            header, entries = _parse(data[:whole], session_id)
            session = replay(header, entries)
            if whole < len(data):
                # A line cut by a crash: dropped, so the next append does not
                # leave it in the middle (spec hito 6, §1.3).
                os.ftruncate(fd, whole)
        except BaseException:
            await log.close()
            raise
        return session, log

    async def summaries(self) -> list[SessionSummary]:
        """Every session that can be read, newest first, without locking
        them: an open one is listed too."""
        try:
            names = [entry.name for entry in os.scandir(self._folder)]
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise SessionError(f"cannot list sessions: {exc.strerror}") from None
        found = []
        for name in names:
            session_id = name.removesuffix(".jsonl")
            if name == session_id or not is_session_id(session_id):
                continue
            summary = self._summary(session_id)
            if summary is not None:
                found.append(summary)
        return sorted(found, key=lambda summary: summary.updated_at, reverse=True)

    async def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            raise _not_found(session_id) from None
        except OSError as exc:
            raise SessionError(
                f"cannot delete session {session_id}: {exc.strerror}"
            ) from None
        try:
            # Locked while it goes: nobody opens it in between.
            _lock(fd, session_id)
            if not _still_named(fd, path):
                raise _not_found(session_id)
            path.unlink()
            _sync_folder(self._folder)
        except OSError as exc:
            raise SessionError(
                f"cannot delete session {session_id}: {exc.strerror}"
            ) from None
        finally:
            os.close(fd)

    def _summary(self, session_id: str) -> SessionSummary | None:
        """The line of /sessions, or None if the file cannot be read."""
        path = self._folder / f"{session_id}.jsonl"
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            return None
        try:
            data = _read(fd)
            updated = datetime.fromtimestamp(os.fstat(fd).st_mtime, UTC)
            header, entries = _parse(data[: _whole_lines(data)], session_id)
        except OSError, SessionError:
            return None
        finally:
            os.close(fd)
        if header.id != session_id:
            return None
        return summarize(header, entries, updated)

    def _path(self, session_id: str) -> Path:
        # Checked before it becomes a file name (spec hito 6, §1.2).
        if not is_session_id(session_id):
            raise _not_found(session_id)
        return self._folder / f"{session_id}.jsonl"


_CREATE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | os.O_NOFOLLOW
_OPEN = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW


def _lock(fd: int, session_id: str) -> None:
    """Lock the open file, or raise `SessionInUse` at once. The lock goes
    when the file is closed or maha dies (spec hito 6, §1.1)."""
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SessionInUse(f"session {session_id} is open in another maha") from None


def _still_named(fd: int, path: Path) -> bool:
    """Whether `path` is still the file that `fd` locked: another maha may
    have deleted it between the open and the lock."""
    try:
        named = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    held = os.fstat(fd)
    return (named.st_dev, named.st_ino) == (held.st_dev, held.st_ino)


def _write(fd: int, path: Path, data: bytes) -> None:
    """All of `data` at the end of the file, then `fsync`: not on the disk is
    not saved."""
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    except OSError as exc:
        raise _cannot_save(path, exc) from None


def _read(fd: int) -> bytes:
    chunks = []
    while chunk := os.read(fd, 1024 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


def _whole_lines(data: bytes) -> int:
    """How many bytes of `data` are whole lines: a last line without its
    "\n" was cut by a crash, because each write ends in one."""
    return data.rfind(b"\n") + 1


def _parse(data: bytes, session_id: str) -> tuple[SessionHeader, list[SessionEntry]]:
    """The header and the entries of whole lines. Raises `SessionCorrupt`."""

    def corrupt(problem: str) -> SessionCorrupt:
        return SessionCorrupt(f"session {session_id}: {problem}")

    lines = data.split(b"\n")[:-1]
    if not lines:
        raise corrupt("empty file")
    try:
        first = json.loads(lines[0])
    except ValueError:
        raise corrupt("line 1 is not a header") from None
    if not isinstance(first, dict) or first.pop("type", None) != "session":
        raise corrupt("line 1 is not a header")
    version = first.pop("version", None)
    if isinstance(version, int) and version > VERSION:
        raise corrupt(f"version {version}, made by a newer maha")
    if version != VERSION:
        raise corrupt(f"unknown version {version!r}")
    try:
        header = SessionHeader.model_validate(first)
    except ValidationError as exc:
        raise corrupt(f"line 1 is not a valid header: {_first(exc)}") from None
    entries = []
    for number, line in enumerate(lines[1:], start=2):
        try:
            entries.append(_ENTRY.validate_json(line))
        except ValidationError as exc:
            raise corrupt(f"line {number} is not valid: {_first(exc)}") from None
    return header, entries


def _first(exc: ValidationError) -> str:
    """The first problem, without echoing the input."""
    error = exc.errors(include_url=False, include_input=False)[0]
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else error["msg"]


def _sync_folder(folder: Path) -> None:
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _not_found(session_id: str) -> SessionNotFound:
    return SessionNotFound(f"no session {session_id}")


def _cannot_save(path: Path, exc: OSError) -> SessionError:
    return SessionError(f"cannot save session {path.stem}: {exc.strerror}")
