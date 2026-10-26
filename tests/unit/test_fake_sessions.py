"""`MemorySessionStore` follows the port (spec hito 6, §1.4 and §4.2)."""

from datetime import UTC, datetime

import pytest

from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import Usage
from mharness.domain.session import (
    MessageEntry,
    ModelEntry,
    SessionHeader,
    SessionInUse,
    SessionNotFound,
    UsageEntry,
)
from mharness.ports.sessions import SessionStore
from tests.fakes.sessions import MemorySessionStore

HEADER = SessionHeader(
    id="20261026-091502-3fa2",
    created_at=datetime(2026, 10, 26, 9, 15, 2, tzinfo=UTC),
    cwd="/home/ana/proyecto",
    provider="opencode-go",
    model="glm-5.3-flash",
    maha="0.6.0",
)
HOLA = Message(role="user", blocks=[TextBlock(text="Hola")])
ANSWER = Message(role="assistant", blocks=[TextBlock(text="Hola, Ana.")])


def test_satisfies_the_port() -> None:
    # mypy checks this assignment against the Protocol.
    store: SessionStore = MemorySessionStore()

    assert store is not None


async def test_what_is_appended_comes_back() -> None:
    store = MemorySessionStore()
    log = await store.create(HEADER)
    await log.append([MessageEntry(message=HOLA), MessageEntry(message=ANSWER)])
    await log.append([UsageEntry(usage=Usage(input_tokens=7)), ModelEntry(model="k")])
    await log.close()

    session, again = await store.open(HEADER.id)

    assert session.messages == [HOLA, ANSWER]
    assert (session.model, session.usage) == ("k", Usage(input_tokens=7))
    await again.close()
    [summary] = await store.summaries()
    assert (summary.id, summary.messages, summary.title) == (HEADER.id, 2, "Hola")


async def test_an_open_session_is_locked() -> None:
    store = MemorySessionStore()
    log = await store.create(HEADER)

    with pytest.raises(SessionInUse):
        await store.open(HEADER.id)
    with pytest.raises(SessionInUse):
        await store.delete(HEADER.id)

    await log.close()
    _, reopened = await store.open(HEADER.id)
    await reopened.close()
    await store.delete(HEADER.id)
    assert await store.summaries() == []


async def test_an_unknown_id_is_not_found() -> None:
    store = MemorySessionStore()

    with pytest.raises(SessionNotFound):
        await store.open("20261026-091502-0000")
    with pytest.raises(SessionNotFound):
        await store.delete("../../etc/passwd")
