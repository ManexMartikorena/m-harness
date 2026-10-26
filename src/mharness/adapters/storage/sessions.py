"""Sessions as JSONL files, one per session (spec hito 6, §1.3 and §1.5).

`<folder>/<id>.jsonl`: a header line, then one `SessionEntry` per line.
Lines are only appended; a turn is one write followed by `fsync`. The folder
is `0700` and the files `0600`: a session keeps all the agent read.

Disk calls are synchronous inside `async def`, as in the file tools: small
writes, and no threads (spec hito 2, §12).
"""

import json
import os
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from mharness.domain.session import (
    Session,
    SessionEntry,
    SessionError,
    SessionHeader,
    SessionNotFound,
    SessionSummary,
    is_session_id,
    replay,
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
            header, entries = _parse(_read(fd), session_id)
            session = replay(header, entries)
        except BaseException:
            await log.close()
            raise
        return session, log

    async def summaries(self) -> list[SessionSummary]:
        raise NotImplementedError

    async def delete(self, session_id: str) -> None:
        raise NotImplementedError

    def _path(self, session_id: str) -> Path:
        # Checked before it becomes a file name (spec hito 6, §1.2).
        if not is_session_id(session_id):
            raise _not_found(session_id)
        return self._folder / f"{session_id}.jsonl"


_CREATE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | os.O_NOFOLLOW
_OPEN = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW


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


def _parse(data: bytes, session_id: str) -> tuple[SessionHeader, list[SessionEntry]]:
    """The header and the entries of a file."""
    lines = data.decode("utf-8").splitlines()
    try:
        first = json.loads(lines[0])
        first.pop("type")
        first.pop("version")
        header = SessionHeader.model_validate(first)
        entries = [_ENTRY.validate_json(line) for line in lines[1:]]
    except (IndexError, KeyError, ValueError, ValidationError) as exc:
        raise SessionError(f"session {session_id} cannot be read: {exc}") from None
    return header, entries


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
