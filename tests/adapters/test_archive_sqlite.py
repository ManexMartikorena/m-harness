"""The archive of a session (spec hito 11, §1.5, and §4, test 12): the
SQLite one, and the fake in memory where they must agree."""

import os
import sqlite3
import stat
import time
from pathlib import Path

import pytest

from mharness.adapters.storage.archive_sqlite import (
    SqliteArchive,
    SqliteArchiveStore,
)
from mharness.domain.archive import (
    ArchiveError,
    ArchiveItem,
    ItemNotFound,
    message_item,
    parse_id,
    search_terms,
)
from mharness.ports.archive import ArchiveStore, ContextArchive
from tests.fakes.archive import MemoryArchive, MemoryArchiveStore

SESSION = "20261117-091502-3fa2"
OTHER = "20261117-091502-0bad"


def output(text: str, position: int = 3, tool: str = "run_command") -> ArchiveItem:
    return ArchiveItem(
        kind="output", position=position, role="tool", tool=tool, text=text
    )


def message(text: str, position: int = 0) -> ArchiveItem:
    return ArchiveItem(kind="message", position=position, role="user", text=text)


@pytest.fixture(params=["sqlite", "memory"])
def archive(request: pytest.FixtureRequest, tmp_path: Path) -> ContextArchive:
    if request.param == "sqlite":
        return SqliteArchive(tmp_path / "archive" / f"{SESSION}.db")
    return MemoryArchive()


# Both, as the port says.


async def test_a_new_archive_is_empty(archive: ContextArchive) -> None:
    assert await archive.empty()
    assert await archive.search("iva", 5) == []


async def test_ids_go_by_kind_and_in_order(archive: ContextArchive) -> None:
    first = await archive.add([output("uno"), message("dos"), output("tres")])
    second = await archive.add([output("cuatro")])

    assert first == ["out-1", "msg-1", "out-2"]
    assert second == ["out-3"]
    assert not await archive.empty()


async def test_a_numbered_item_keeps_its_number(archive: ContextArchive) -> None:
    ids = await archive.add([message_item(6, "user", "siete"), output("uno")])

    assert ids == ["msg-7", "out-1"]
    assert (await archive.read("msg-7", 1, 5)).lines == ["siete"]


async def test_adding_a_numbered_item_again_adds_nothing(
    archive: ContextArchive,
) -> None:
    # Archiving the same message twice, after a Ctrl+C (spec hito 11, §1.10).
    await archive.add([message_item(0, "user", "hola iva")])
    again = await archive.add([message_item(0, "user", "otra cosa")])

    assert again == ["msg-1"]
    assert (await archive.read("msg-1", 1, 5)).lines == ["hola iva"]
    assert len(await archive.search("iva otra", 5)) == 1


async def test_a_summary_is_searched_and_read(archive: ContextArchive) -> None:
    summary = ArchiveItem(
        kind="summary",
        position=14,
        role="assistant",
        text="arreglado el IVA",
        number=15,
    )
    assert await archive.add([summary]) == ["sum-15"]

    [hit] = await archive.search("iva", 5)
    assert (hit.id, hit.kind) == ("sum-15", "summary")


async def test_adding_nothing_gives_nothing(archive: ContextArchive) -> None:
    assert await archive.add([]) == []
    assert await archive.empty()


async def test_search_finds_the_item_with_the_words(archive: ContextArchive) -> None:
    await archive.add(
        [
            output("pytest: 3 passed"),
            message("Arregla el redondeo del IVA reducido", position=0),
            output("ruff: all checks passed"),
        ]
    )

    hits = await archive.search("redondeo IVA", 5)

    assert hits[0].id == "msg-1"
    assert hits[0].role == "user"
    assert hits[0].position == 0
    assert "redondeo" in hits[0].snippet


async def test_search_takes_at_most_the_limit(archive: ContextArchive) -> None:
    await archive.add([output(f"error {i}") for i in range(8)])

    assert len(await archive.search("error", 5)) == 5


async def test_search_ignores_what_is_not_a_word(archive: ContextArchive) -> None:
    await archive.add([output("total = 21.50")])

    # FTS5 operators and quotes from the model never break the query.
    assert await archive.search('" OR ) NEAR(', 5) == []
    assert [hit.id for hit in await archive.search('total" AND', 5)] == ["out-1"]


async def test_read_gives_lines_from_an_offset(archive: ContextArchive) -> None:
    [item] = await archive.add([output("\n".join(f"line {i}" for i in range(1, 11)))])

    part = await archive.read(item, 4, 3)

    assert part.lines == ["line 4", "line 5", "line 6"]
    assert (part.offset, part.total) == (4, 10)


async def test_read_past_the_end_gives_no_lines(archive: ContextArchive) -> None:
    [item] = await archive.add([output("a\nb")])

    part = await archive.read(item, 9, 5)

    assert part.lines == []
    assert part.total == 2


async def test_reading_an_unknown_id_is_not_found(archive: ContextArchive) -> None:
    await archive.add([output("a")])

    with pytest.raises(ItemNotFound):
        await archive.read("out-9", 1, 10)
    with pytest.raises(ItemNotFound):
        await archive.read("../etc/passwd", 1, 10)


async def test_rebuild_keeps_only_the_items_given(archive: ContextArchive) -> None:
    await archive.add([output("viejo")])

    await archive.rebuild([message("nuevo")])

    assert [hit.id for hit in await archive.search("nuevo", 5)] == ["msg-1"]
    assert await archive.search("viejo", 5) == []


# SQLite only.


async def test_nothing_touches_the_disk_until_the_first_item(tmp_path: Path) -> None:
    store = SqliteArchiveStore(tmp_path / "archive")
    archive = store.open(SESSION)

    assert await archive.empty()
    assert await archive.search("x", 5) == []
    with pytest.raises(ItemNotFound):
        await archive.read("out-1", 1, 1)

    assert not (tmp_path / "archive").exists()


async def test_the_file_is_private(tmp_path: Path) -> None:
    folder = tmp_path / "archive"
    await SqliteArchiveStore(folder).open(SESSION).add([output("secreto")])

    path = folder / f"{SESSION}.db"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


async def test_it_lasts_across_openings(tmp_path: Path) -> None:
    store = SqliteArchiveStore(tmp_path)
    await store.open(SESSION).add([output("persistente")])

    hits = await SqliteArchiveStore(tmp_path).open(SESSION).search("persistente", 5)

    assert [hit.id for hit in hits] == ["out-1"]


async def test_search_finds_words_without_their_accents(tmp_path: Path) -> None:
    archive = SqliteArchive(tmp_path / f"{SESSION}.db")
    await archive.add([message("La función calcula el IVA")])

    assert [hit.id for hit in await archive.search("funcion", 5)] == ["msg-1"]


async def test_the_best_match_comes_first(tmp_path: Path) -> None:
    archive = SqliteArchive(tmp_path / f"{SESSION}.db")
    long = output("iva " + "relleno " * 200)
    await archive.add([long, output("iva reducido iva 4"), output("nada")])

    hits = await archive.search("iva reducido", 5)

    assert [hit.id for hit in hits] == ["out-2", "out-1"]


async def test_a_broken_file_is_an_archive_error(tmp_path: Path) -> None:
    path = tmp_path / f"{SESSION}.db"
    path.write_bytes(b"esto no es una base de datos" * 100)
    archive = SqliteArchive(path)

    with pytest.raises(ArchiveError, match="failed"):
        await archive.search("x", 5)
    with pytest.raises(ArchiveError):
        await archive.add([output("x")])


async def test_a_broken_file_is_made_again_by_rebuild(tmp_path: Path) -> None:
    path = tmp_path / f"{SESSION}.db"
    path.write_bytes(b"roto" * 1000)
    archive = SqliteArchive(path)

    await archive.rebuild([message("de nuevo")])

    assert [hit.id for hit in await archive.search("nuevo", 5)] == ["msg-1"]


async def test_another_schema_is_an_archive_error(tmp_path: Path) -> None:
    path = tmp_path / f"{SESSION}.db"
    # `with` on a connection commits, but does not close it.
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA user_version = 99")
        db.commit()
    finally:
        db.close()

    with pytest.raises(ArchiveError, match="schema 99"):
        await SqliteArchive(path).empty()


async def test_a_failed_add_adds_nothing(tmp_path: Path) -> None:
    archive = SqliteArchive(tmp_path / f"{SESSION}.db")
    await archive.add([output("primero")])
    bad = ArchiveItem.model_construct(
        kind="output", position=0, role="tool", tool=None, text=None
    )

    with pytest.raises(ArchiveError):
        await archive.add([output("segundo"), bad])

    assert await archive.search("segundo", 5) == []
    assert await archive.add([output("tercero")]) == ["out-2"]


async def test_the_store_moves_and_deletes(tmp_path: Path) -> None:
    store = SqliteArchiveStore(tmp_path)
    await store.open(SESSION).add([output("x")])

    await store.move(SESSION, OTHER)
    assert await store.open(SESSION).empty()
    assert not await store.open(OTHER).empty()

    await store.delete(OTHER)
    assert os.listdir(tmp_path) == []
    # Without an archive, nothing to do.
    await store.delete(SESSION)
    await store.move(SESSION, OTHER)


def test_the_store_takes_only_session_ids(tmp_path: Path) -> None:
    with pytest.raises(ArchiveError, match="invalid session id"):
        SqliteArchiveStore(tmp_path).open("../../etc/passwd")


def test_both_stores_follow_the_port(tmp_path: Path) -> None:
    stores: list[ArchiveStore] = [SqliteArchiveStore(tmp_path), MemoryArchiveStore()]
    assert len(stores) == 2


# The domain's helpers.


def test_ids_are_parsed_strictly() -> None:
    assert parse_id("out-17") == ("output", 17)
    assert parse_id("msg-1") == ("message", 1)
    assert parse_id("sum-40") == ("summary", 40)
    for wrong in ("out-0", "out-01", "out-", "foo-1", "out-1 ", "OUT-1"):
        assert parse_id(wrong) is None


def test_search_terms_are_the_words() -> None:
    assert search_terms('test "iva" 4%') == ["test", "iva", "4"]
    assert search_terms("año café") == ["año", "café"]


async def test_a_hit_shows_the_text_as_it_is(tmp_path: Path) -> None:
    # Seen with a real model (spec hito 11, §12): marks around the match
    # ended up quoted as part of the log line, "[ERROR]".
    archive = SqliteArchive(tmp_path / f"{SESSION}.db")
    await archive.add([output("013458 ERROR payment failed code=PX-4471")])

    [hit] = await archive.search("ERROR", 5)

    assert hit.snippet == "013458 ERROR payment failed code=PX-4471"


async def test_a_hit_in_a_huge_output_comes_at_once(tmp_path: Path) -> None:
    # Seen at the hand verification of hito 11: FTS5's snippet() grows with
    # the square of the matches, and over an output of 400,000 lines with
    # words in every one it took more than two minutes. 10,000 lines say
    # the same: 1.9 s with snippet().
    archive = SqliteArchive(tmp_path / f"{SESSION}.db")
    text = "".join(f"linea numero {n}\n" for n in range(1, 10_001))
    await archive.add([output(text)])

    started = time.monotonic()
    [hit] = await archive.search("linea numero 1234", 5)

    assert time.monotonic() - started < 1.0
    assert "linea numero 1234\n" in hit.snippet + "\n"


async def test_a_search_that_takes_too_long_is_an_archive_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mharness.adapters.storage import archive_sqlite

    archive = SqliteArchive(tmp_path / f"{SESSION}.db")
    await archive.add([output("iva " * 1000)])
    monkeypatch.setattr(archive_sqlite, "SEARCH_TIME_LIMIT", 0.0)
    monkeypatch.setattr(archive_sqlite, "_CLOCK_EVERY", 1)

    with pytest.raises(ArchiveError, match="search took more than"):
        await archive.search("iva", 5)
