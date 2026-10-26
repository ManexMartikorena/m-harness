"""`JsonlSessionStore` over `tmp_path` (spec hito 6, §1.3, §1.5 and §4.3)."""

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mharness.adapters.storage import JsonlSessionStore
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.session import (
    MessageEntry,
    ModelEntry,
    SessionError,
    SessionHeader,
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
