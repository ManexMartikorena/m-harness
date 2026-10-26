"""The types of a session (spec hito 6, §1.2 and §4.1), without the disk."""

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.session import (
    MessageEntry,
    ModelEntry,
    SessionCorrupt,
    SessionEntry,
    SessionError,
    SessionHeader,
    SessionInUse,
    SessionNotFound,
    UsageEntry,
    check_history,
    is_session_id,
    session_id,
)

ENTRY: TypeAdapter[SessionEntry] = TypeAdapter(SessionEntry)


def test_the_id_reads_and_sorts_by_date() -> None:
    created = datetime(2026, 10, 26, 9, 15, 2, tzinfo=UTC)

    assert session_id(created, "3fa2") == "20261026-091502-3fa2"


@pytest.mark.parametrize(
    "text", ["20261026-091502-3fa2", "19991231-235959-0000", "20261026-091502-ffff"]
)
def test_valid_ids(text: str) -> None:
    assert is_session_id(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "../../etc/passwd",
        "20261026-091502-3FA2",
        "20261026-091502-3fa2/x",
        "20261026-091502-3fa",
        "20261026-091502-3fa2 ",
        "20261026_091502_3fa2",
        "x20261026-091502-3fa2",
    ],
)
def test_other_text_is_not_an_id(text: str) -> None:
    # It becomes a file name: nothing else may reach the disk.
    assert not is_session_id(text)


def test_entries_are_validated_by_type() -> None:
    message = Message(role="user", blocks=[TextBlock(text="Hola")])
    for entry in (
        MessageEntry(message=message),
        UsageEntry(usage=Usage(input_tokens=742, output_tokens=31)),
        ModelEntry(model="kimi-k3"),
    ):
        assert ENTRY.validate_json(entry.model_dump_json()) == entry

    with pytest.raises(ValidationError):
        ENTRY.validate_python({"type": "approval", "scope": "run_command:ls"})


def test_the_header_needs_every_field_and_is_immutable() -> None:
    header = SessionHeader(
        id="20261026-091502-3fa2",
        created_at=datetime(2026, 10, 26, 9, 15, 2, tzinfo=UTC),
        cwd="/home/ana/proyecto",
        provider="opencode-go",
        model="glm-5.3-flash",
        maha="0.6.0",
    )

    with pytest.raises(ValidationError):
        header.model = "kimi-k3"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        SessionHeader.model_validate({"id": header.id})


def test_every_error_is_a_session_error() -> None:
    for error in (SessionNotFound, SessionInUse, SessionCorrupt):
        assert issubclass(error, SessionError)


# A history the API accepts (spec hito 6, §1.2 and §4.1.2).


def user(text: str = "Hola") -> Message:
    return Message(role="user", blocks=[TextBlock(text=text)])


def calls(*ids: str) -> Message:
    return Message(
        role="assistant",
        blocks=[
            TextBlock(text="Miro."),
            *(ToolCallBlock(id=id, name="read_file", arguments="{}") for id in ids),
        ],
    )


def results(*ids: str) -> Message:
    return Message(
        role="tool", blocks=[ToolResultBlock(call_id=id, content="ok") for id in ids]
    )


def answer(text: str = "Hecho.") -> Message:
    return Message(role="assistant", blocks=[TextBlock(text=text)])


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [user(), answer()],
        [user(), calls("c1", "c2"), results("c1", "c2"), answer()],
        # A turn denied or at the step limit ends on its results.
        [user(), calls("c1"), results("c1")],
        [user(), calls("c1"), results("c1"), user("Sigue"), answer()],
    ],
)
def test_a_valid_history(messages: list[Message]) -> None:
    check_history(messages)


@pytest.mark.parametrize(
    ("messages", "problem"),
    [
        ([user(), calls("c1")], "call c1 has no result"),
        ([user(), calls("c1"), answer()], "call c1 has no result"),
        ([user(), calls("c1", "c2"), results("c1")], "call c2 has no result"),
        ([user(), results("c1")], "result c1 without its call"),
        ([user(), calls("c1"), results("c1", "c9")], "result c9 without its call"),
        ([user(), calls("c1"), results("c1", "c1")], "result c1 without its call"),
        (
            [user(), calls("c1"), Message(role="tool", blocks=[TextBlock(text="x")])],
            "a tool message holds only results",
        ),
    ],
)
def test_a_broken_history(messages: list[Message], problem: str) -> None:
    with pytest.raises(SessionCorrupt, match=f"^history: {problem}$"):
        check_history(messages)
