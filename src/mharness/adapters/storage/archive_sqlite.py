"""The archive of each session in SQLite, with FTS5 to search it (spec hito
11, §1.5).

`<folder>/<id>.db`, `0600`, in a `0700` folder, as the sessions: it holds
what the session holds. Created with the first item, never before. Each
call opens its own connection in a thread (`asyncio.to_thread`): the loop
does not wait for the disk, and SQLite's connections are not shared
between threads. A write is one transaction: all or nothing.
"""

import asyncio
import contextlib
import os
import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path

from mharness.domain.archive import (
    ArchiveError,
    ArchiveItem,
    Hit,
    ItemKind,
    ItemLines,
    ItemNotFound,
    item_id,
    parse_id,
    search_terms,
)
from mharness.domain.session import is_session_id

# The schema; another one is an index of another maha, made again.
SCHEMA_VERSION = 1

# One statement each: `executescript` would commit the transaction.
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS items ("
    " id INTEGER PRIMARY KEY, kind TEXT NOT NULL, number INTEGER NOT NULL,"
    " position INTEGER NOT NULL, role TEXT NOT NULL, tool TEXT,"
    " text TEXT NOT NULL, UNIQUE (kind, number))",
    "CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5("
    " text, content='items', content_rowid='id',"
    " tokenize='unicode61 remove_diacritics 2')",
)

# Words around a match in each hit.
_SNIPPET_TOKENS = 40


class SqliteArchive:
    """One session's archive, in `path`."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def add(self, items: Sequence[ArchiveItem]) -> list[str]:
        if not items:
            return []
        return await asyncio.to_thread(self._add, list(items))

    async def search(self, query: str, limit: int) -> list[Hit]:
        terms = search_terms(query)
        if not terms or limit < 1:
            return []
        return await asyncio.to_thread(self._search, terms, limit)

    async def read(self, item: str, offset: int, limit: int) -> ItemLines:
        return await asyncio.to_thread(self._read, item, offset, limit)

    async def empty(self) -> bool:
        return await asyncio.to_thread(self._empty)

    async def rebuild(self, items: Sequence[ArchiveItem]) -> None:
        await asyncio.to_thread(self._rebuild, list(items))

    def _add(self, items: list[ArchiveItem]) -> list[str]:
        with self._connect(create=True) as db:
            ids = [_insert(db, item) for item in items]
        return ids

    def _search(self, terms: list[str], limit: int) -> list[Hit]:
        if not self._path.exists():
            return []
        # Each word quoted: a word is never an operator (`AND`, `NEAR`).
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        with self._connect() as db:
            rows = db.execute(
                "SELECT items.kind, items.number, items.position, items.role,"
                " items.tool,"
                " snippet(items_fts, 0, '[', ']', '…', ?)"
                " FROM items_fts JOIN items ON items.id = items_fts.rowid"
                " WHERE items_fts MATCH ? ORDER BY bm25(items_fts) LIMIT ?",
                (_SNIPPET_TOKENS, match, limit),
            ).fetchall()
        return [
            Hit(
                id=item_id(kind, number),
                kind=kind,
                position=position,
                role=role,
                tool=tool,
                snippet=snippet,
            )
            for kind, number, position, role, tool, snippet in rows
        ]

    def _read(self, item: str, offset: int, limit: int) -> ItemLines:
        parsed = parse_id(item)
        if parsed is None or not self._path.exists():
            raise ItemNotFound(f"no archived item {item}")
        kind, number = parsed
        with self._connect() as db:
            row = db.execute(
                "SELECT text FROM items WHERE kind = ? AND number = ?",
                (kind, number),
            ).fetchone()
        if row is None:
            raise ItemNotFound(f"no archived item {item}")
        lines: list[str] = row[0].split("\n")
        first = max(offset, 1)
        return ItemLines(
            id=item,
            offset=first,
            lines=lines[first - 1 : first - 1 + max(limit, 0)],
            total=len(lines),
        )

    def _empty(self) -> bool:
        if not self._path.exists():
            return True
        with self._connect() as db:
            return db.execute("SELECT 1 FROM items LIMIT 1").fetchone() is None

    def _rebuild(self, items: list[ArchiveItem]) -> None:
        _remove(self._path)
        if items:
            self._add(items)

    @contextlib.contextmanager
    def _connect(self, *, create: bool = False) -> Iterator[sqlite3.Connection]:
        """A connection in a transaction, committed if nothing failed. Any
        failure of SQLite or the disk is an `ArchiveError`."""
        try:
            if create:
                self._create()
            db = sqlite3.connect(self._path, timeout=10, isolation_level=None)
        except (OSError, sqlite3.Error) as exc:
            raise self._error(exc) from None
        try:
            db.execute("BEGIN IMMEDIATE" if create else "BEGIN")
            if create:
                _ensure_schema(db)
            else:
                _check_schema(db, self._path)
            yield db
            db.execute("COMMIT")
        except sqlite3.Error as exc:
            with contextlib.suppress(sqlite3.Error):
                db.execute("ROLLBACK")
            raise self._error(exc) from None
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def _create(self) -> None:
        """The folder `0700` and the file `0600`, before SQLite creates it
        with the umask."""
        folder = self._path.parent
        folder.mkdir(parents=True, exist_ok=True)
        folder.chmod(0o700)
        fd = os.open(self._path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)

    def _error(self, exc: Exception) -> ArchiveError:
        if isinstance(exc, ArchiveError):
            return exc
        detail = exc.strerror if isinstance(exc, OSError) else str(exc)
        return ArchiveError(f"the archive {self._path.name} failed: {detail}")


class SqliteArchiveStore:
    """The archives of every session, in `folder`."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def open(self, session_id: str) -> SqliteArchive:
        return SqliteArchive(self._path(session_id))

    async def move(self, old: str, new: str) -> None:
        source, target = self._path(old), self._path(new)
        try:
            if source.exists():
                source.rename(target)
        except OSError as exc:
            raise ArchiveError(
                f"cannot move the archive of {old}: {exc.strerror}"
            ) from None

    async def delete(self, session_id: str) -> None:
        try:
            _remove(self._path(session_id))
        except OSError as exc:
            raise ArchiveError(
                f"cannot delete the archive of {session_id}: {exc.strerror}"
            ) from None

    def _path(self, session_id: str) -> Path:
        # Checked here too: an id is part of a path.
        if not is_session_id(session_id):
            raise ArchiveError(f"invalid session id {session_id!r}")
        return self._folder / f"{session_id}.db"


def _insert(db: sqlite3.Connection, item: ArchiveItem) -> str:
    kind: ItemKind = item.kind
    (last,) = db.execute(
        "SELECT COALESCE(MAX(number), 0) FROM items WHERE kind = ?", (kind,)
    ).fetchone()
    number = last + 1
    cursor = db.execute(
        "INSERT INTO items (kind, number, position, role, tool, text)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (kind, number, item.position, item.role, item.tool, item.text),
    )
    db.execute(
        "INSERT INTO items_fts (rowid, text) VALUES (?, ?)",
        (cursor.lastrowid, item.text),
    )
    return item_id(kind, number)


def _ensure_schema(db: sqlite3.Connection) -> None:
    (version,) = db.execute("PRAGMA user_version").fetchone()
    if version == 0:
        for statement in _SCHEMA:
            db.execute(statement)
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    elif version != SCHEMA_VERSION:
        raise ArchiveError(f"the archive has schema {version}, not {SCHEMA_VERSION}")


def _check_schema(db: sqlite3.Connection, path: Path) -> None:
    (version,) = db.execute("PRAGMA user_version").fetchone()
    if version != SCHEMA_VERSION:
        raise ArchiveError(
            f"the archive {path.name} has schema {version}, not {SCHEMA_VERSION}"
        )


def _remove(path: Path) -> None:
    """The file and what SQLite leaves next to it."""
    for each in (path, path.with_name(path.name + "-journal")):
        each.unlink(missing_ok=True)
