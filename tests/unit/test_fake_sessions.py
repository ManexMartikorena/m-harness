"""`MemorySessionStore` follows the port (spec hito 6, §1.4 and §4.2)."""

from datetime import UTC, datetime

import pytest

from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import Usage
from mharness.domain.session import (
    MessageEntry,
    ModelEntry,
    SessionError,
    SessionExists,
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


# Behaves as JsonlSessionStore where application tests rely on it (final
# audit of hito 6, 8).


async def test_creating_an_existing_session_is_a_clash() -> None:
    store = MemorySessionStore()
    await (await store.create(HEADER)).close()

    with pytest.raises(SessionExists):
        await store.create(HEADER)


async def test_a_closed_log_takes_no_more() -> None:
    log = await MemorySessionStore().create(HEADER)
    await log.close()

    with pytest.raises(SessionError, match="is closed"):
        await log.append([MessageEntry(message=HOLA)])


async def test_closing_twice_does_not_free_another_lock() -> None:
    store = MemorySessionStore()
    first = await store.create(HEADER)
    await first.close()
    _, second = await store.open(HEADER.id)

    await first.close()

    with pytest.raises(SessionInUse):
        await store.open(HEADER.id)
    await second.close()


async def test_entries_go_through_json() -> None:
    # As on the disk: what cannot be written as JSON fails here too.
    store = MemorySessionStore()
    log = await store.create(HEADER)
    odd = Message(role="user", blocks=[TextBlock(text="caf\udce9.txt")])

    await log.append([MessageEntry(message=odd)])

    assert store.sessions[HEADER.id].entries == [MessageEntry(message=odd)]
