"""`JsonlSessionStore` over `tmp_path` (spec hito 6, §1.3, §1.5 and §4.3)."""

import fcntl
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mharness.adapters.storage import JsonlSessionStore, sessions
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.session import (
    MessageEntry,
    ModelEntry,
    SessionCorrupt,
    SessionError,
    SessionHeader,
    SessionInUse,
    SessionNotFound,
    UsageEntry,
)
from mharness.ports.sessions import SessionStore

HEADER = SessionHeader(
    id="20261026-091502-3fa2",
    created_at=datetime(2026, 10, 26, 9, 15, 2, tzinfo=UTC),
    cwd="/home/ana/proyecto",
    provider="opencode-go",
    model="glm-5.3-flash",
    maha="0.6.0",
)
HOLA = Message(role="user", blocks=[TextBlock(text="Hola, soy Ana")])
CALL = Message(
    role="assistant",
    blocks=[ToolCallBlock(id="c1", name="read_file", arguments='{"path": "a"}')],
)
RESULT = Message(role="tool", blocks=[ToolResultBlock(call_id="c1", content="ok")])
ANSWER = Message(role="assistant", blocks=[TextBlock(text="Hola, Ana.")])


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "maha" / "sessions"


def file_of(folder: Path, session_id: str = HEADER.id) -> Path:
    return folder / f"{session_id}.jsonl"


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def exists(path: Path) -> bool:
    return path.exists()


def test_satisfies_the_port(folder: Path) -> None:
    # mypy checks this assignment against the Protocol.
    store: SessionStore = JsonlSessionStore(folder)

    assert store is not None


async def test_what_is_appended_comes_back(folder: Path) -> None:
    store = JsonlSessionStore(folder)
    log = await store.create(HEADER)
    await log.append([MessageEntry(message=m) for m in (HOLA, CALL, RESULT, ANSWER)])
    await log.append([UsageEntry(usage=Usage(input_tokens=742, output_tokens=31))])
    await log.append([ModelEntry(model="kimi-k3")])
    await log.close()

    session, again = await store.open(HEADER.id)
    await again.close()

    assert session.header == HEADER
    assert session.messages == [HOLA, CALL, RESULT, ANSWER]
    assert session.model == "kimi-k3"
    assert session.usage == Usage(input_tokens=742, output_tokens=31)


async def test_the_file_is_a_header_and_one_entry_per_line(folder: Path) -> None:
    log = await JsonlSessionStore(folder).create(HEADER)
    await log.append([MessageEntry(message=HOLA), ModelEntry(model="kimi-k3")])
    await log.close()

    lines = file_of(folder).read_text(encoding="utf-8").splitlines()

    assert json.loads(lines[0]) == {
        "type": "session",
        "version": 1,
        "id": HEADER.id,
        "created_at": "2026-10-26T09:15:02Z",
        "cwd": "/home/ana/proyecto",
        "provider": "opencode-go",
        "model": "glm-5.3-flash",
        "maha": "0.6.0",
    }
    assert json.loads(lines[1])["type"] == "message"
    assert json.loads(lines[2]) == {"type": "model", "model": "kimi-k3"}
    assert len(lines) == 3


async def test_only_the_user_can_read_them(folder: Path) -> None:
    # A session keeps all the agent read, also an approved secret.
    previous = os.umask(0)
    try:
        log = await JsonlSessionStore(folder).create(HEADER)
        await log.close()
    finally:
        os.umask(previous)

    assert mode(folder) == 0o700
    assert mode(file_of(folder)) == 0o600


@pytest.mark.parametrize("session_id", ["../../etc/passwd", "x", "", "a/b"])
async def test_an_id_of_another_form_never_reaches_the_disk(
    folder: Path, session_id: str
) -> None:
    store = JsonlSessionStore(folder)

    with pytest.raises(SessionNotFound):
        await store.open(session_id)
    assert not exists(folder)


async def test_a_missing_session_is_not_found(folder: Path) -> None:
    with pytest.raises(SessionNotFound, match="no session 20261026-091502-0000"):
        await JsonlSessionStore(folder).open("20261026-091502-0000")


async def test_a_failed_fsync_is_an_error(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not on the disk is not saved.
    log = await JsonlSessionStore(folder).create(HEADER)

    def broken(fd: int) -> None:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "fsync", broken)
    with pytest.raises(SessionError, match=r"cannot save session .*Input/output error"):
        await log.append([MessageEntry(message=HOLA)])
    await log.close()


# A file cut by a crash, or that is not a session (spec hito 6, §1.3).


async def saved(folder: Path, *messages: Message) -> Path:
    log = await JsonlSessionStore(folder).create(HEADER)
    await log.append([MessageEntry(message=m) for m in messages])
    await log.close()
    return file_of(folder)


def add_bytes(path: Path, data: bytes) -> None:
    with path.open("ab") as file:
        file.write(data)


def set_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def lines_of(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


async def test_a_last_line_cut_by_a_crash_is_ignored_and_dropped(folder: Path) -> None:
    path = await saved(folder, HOLA, ANSWER)
    add_bytes(path, b'{"type": "message", "message": {"role": "us')
    store = JsonlSessionStore(folder)

    session, log = await store.open(HEADER.id)
    assert session.messages == [HOLA, ANSWER]
    # Dropped before appending, so it never ends up in the middle.
    await log.append([MessageEntry(message=HOLA)])
    await log.close()

    again, log = await store.open(HEADER.id)
    await log.close()
    assert again.messages == [HOLA, ANSWER, HOLA]
    assert len(lines_of(path)) == 4


async def test_a_broken_line_in_the_middle_is_corrupt(folder: Path) -> None:
    path = await saved(folder, HOLA, ANSWER)
    lines = lines_of(path)
    set_lines(path, [lines[0], '{"type": "message", "mess', lines[2]])

    with pytest.raises(SessionCorrupt, match=f"^session {HEADER.id}: line 2 "):
        await JsonlSessionStore(folder).open(HEADER.id)


async def test_a_newer_version_is_refused_with_a_clear_message(folder: Path) -> None:
    path = await saved(folder, HOLA, ANSWER)
    lines = lines_of(path)
    first = json.loads(lines[0]) | {"version": 2}
    set_lines(path, [json.dumps(first), *lines[1:]])

    with pytest.raises(
        SessionCorrupt, match=f"^session {HEADER.id}: version 2, made by a newer maha$"
    ):
        await JsonlSessionStore(folder).open(HEADER.id)


@pytest.mark.parametrize(
    "lines",
    [
        [],
        ["no es json"],
        ['{"type": "message"}'],
        ['{"type": "session", "version": 1, "id": "x"}'],
        ['{"type": "session", "id": "x"}'],
        ['{"type": "session", "version": "1"}'],
    ],
)
async def test_without_a_valid_header_it_is_corrupt(
    folder: Path, lines: list[str]
) -> None:
    set_lines(file_of(folder), lines)

    with pytest.raises(SessionCorrupt, match=f"^session {HEADER.id}: "):
        await JsonlSessionStore(folder).open(HEADER.id)


async def test_a_history_the_model_would_refuse_is_corrupt(folder: Path) -> None:
    await saved(folder, HOLA, CALL)

    with pytest.raises(SessionCorrupt, match="call c1 has no result"):
        await JsonlSessionStore(folder).open(HEADER.id)


# The lock: one maha per session (spec hito 6, §1.4 and §4.3.5). Two stores
# over the same folder stand for two maha: flock locks open files, not
# processes.


async def test_a_new_session_is_locked_until_it_is_closed(folder: Path) -> None:
    log = await JsonlSessionStore(folder).create(HEADER)
    other = JsonlSessionStore(folder)

    with pytest.raises(SessionInUse, match="is open in another maha"):
        await other.open(HEADER.id)

    await log.close()
    _, reopened = await other.open(HEADER.id)
    await reopened.close()


async def test_an_opened_session_is_locked_until_it_is_closed(folder: Path) -> None:
    await saved(folder, HOLA, ANSWER)
    _, log = await JsonlSessionStore(folder).open(HEADER.id)

    with pytest.raises(SessionInUse):
        await JsonlSessionStore(folder).open(HEADER.id)

    await log.close()
    _, again = await JsonlSessionStore(folder).open(HEADER.id)
    await again.close()


async def test_a_session_deleted_while_opening_is_not_found(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Between opening the file and locking it, another maha deleted it: the
    # lock is on a file that no name points to any more.
    path = await saved(folder, HOLA, ANSWER)
    lock = fcntl.flock

    def deleted_first(fd: int, operation: int) -> None:
        path.unlink()
        lock(fd, operation)

    monkeypatch.setattr(fcntl, "flock", deleted_first)

    with pytest.raises(SessionNotFound):
        await JsonlSessionStore(folder).open(HEADER.id)


# /sessions and /delete (spec hito 6, §1.5 and §4.3.7).


def header(session_id: str, cwd: str = "/home/ana/proyecto") -> SessionHeader:
    return HEADER.model_copy(update={"id": session_id, "cwd": cwd})


def touch(path: Path, seconds: float) -> None:
    os.utime(path, (seconds, seconds))


async def test_without_sessions_the_list_is_empty(folder: Path) -> None:
    assert await JsonlSessionStore(folder).summaries() == []


async def test_the_list_is_newest_first_with_title_and_messages(folder: Path) -> None:
    store = JsonlSessionStore(folder)
    for session_id, cwd, text in [
        ("20261025-174233-b01c", "/home/ana/web", "explícame el router"),
        ("20261026-091502-3fa2", "/home/ana/proyecto", "arregla el test\ny más"),
    ]:
        log = await store.create(header(session_id, cwd))
        user = Message(role="user", blocks=[TextBlock(text=text)])
        await log.append([MessageEntry(message=user), MessageEntry(message=ANSWER)])
        await log.close()
    # The older file was used last.
    touch(file_of(folder, "20261026-091502-3fa2"), 1_000)
    touch(file_of(folder, "20261025-174233-b01c"), 2_000)

    found = await store.summaries()

    assert [(s.id, s.cwd, s.messages, s.title) for s in found] == [
        ("20261025-174233-b01c", "/home/ana/web", 2, "explícame el router"),
        ("20261026-091502-3fa2", "/home/ana/proyecto", 2, "arregla el test"),
    ]
    assert found[0].updated_at == datetime.fromtimestamp(2_000, UTC)


async def test_the_list_skips_what_it_cannot_read(folder: Path) -> None:
    await saved(folder, HOLA, ANSWER)
    set_lines(file_of(folder, "20261026-091502-0000"), ["no es json"])
    set_lines(folder / "notas.jsonl", ["{}"])
    set_lines(folder / "20261026-091502-1111.txt", ["{}"])

    found = await JsonlSessionStore(folder).summaries()

    assert [s.id for s in found] == [HEADER.id]


async def test_an_open_session_is_listed_and_a_broken_history_too(
    folder: Path,
) -> None:
    # Listed, so it can be deleted.
    await saved(folder, HOLA, CALL)
    log = await JsonlSessionStore(folder).create(header("20261026-091502-2222"))

    found = await JsonlSessionStore(folder).summaries()
    await log.close()

    assert sorted(s.id for s in found) == ["20261026-091502-2222", HEADER.id]


async def test_delete_removes_the_file(folder: Path) -> None:
    path = await saved(folder, HOLA, ANSWER)
    store = JsonlSessionStore(folder)

    await store.delete(HEADER.id)

    assert not exists(path)
    assert await store.summaries() == []
    with pytest.raises(SessionNotFound):
        await store.delete(HEADER.id)


async def test_an_open_session_is_not_deleted(folder: Path) -> None:
    await saved(folder, HOLA, ANSWER)
    _, log = await JsonlSessionStore(folder).open(HEADER.id)

    with pytest.raises(SessionInUse):
        await JsonlSessionStore(folder).delete(HEADER.id)

    await log.close()
    assert exists(file_of(folder))


async def test_delete_with_another_form_of_id_touches_nothing(folder: Path) -> None:
    await saved(folder, HOLA, ANSWER)

    with pytest.raises(SessionNotFound):
        await JsonlSessionStore(folder).delete(f"../sessions/{HEADER.id}")
    assert exists(file_of(folder))


# Every disk failure is a SessionError: the conversation catches only that
# and goes on (spec hito 6, §1.6).


async def test_a_disk_failure_creating_is_a_session_error(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(folder: Path) -> None:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(sessions, "_sync_folder", broken)

    with pytest.raises(SessionError, match=r"cannot save session .*Input/output"):
        await JsonlSessionStore(folder).create(HEADER)
    # Not left half made: the conversation tries again with another id.
    assert not exists(file_of(folder))


async def test_a_disk_failure_opening_is_a_session_error(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await saved(folder, HOLA, ANSWER)

    def broken(fd: int) -> bytes:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(sessions, "_read", broken)

    with pytest.raises(SessionError, match=r"cannot open session .*Input/output"):
        await JsonlSessionStore(folder).open(HEADER.id)
