"""A session in Markdown (spec hito 8, §1.15)."""

from datetime import UTC, datetime
from decimal import Decimal

from mharness.adapters.cli.export import markdown
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.session import Session, SessionHeader

HEADER = SessionHeader(
    id="20261030-101500-3fa2",
    created_at=datetime(2026, 10, 30, 10, 15, tzinfo=UTC),
    cwd="/home/ana/proyecto",
    provider="opencode-go",
    model="glm-5.3-flash",
    maha="0.8.0",
)


def session(*messages: Message, cost: str = "0.0012") -> Session:
    return Session(
        header=HEADER,
        messages=list(messages),
        model="glm-5.3-flash",
        usage=Usage(input_tokens=1200, output_tokens=80),
        cost=Decimal(cost),
    )


def user(text: str) -> Message:
    return Message(role="user", blocks=[TextBlock(text=text)])


def said(text: str, *, interrupted: bool = False) -> Message:
    return Message(
        role="assistant", blocks=[TextBlock(text=text)], interrupted=interrupted
    )


def test_a_conversation_in_markdown() -> None:
    call = ToolCallBlock(id="c1", name="read_file", arguments='{"path": "README.md"}')
    text = markdown(
        session(
            user("¿Qué dice el README?\nEn corto."),
            Message(role="assistant", blocks=[TextBlock(text="Lo miro."), call]),
            Message(
                role="tool",
                blocks=[ToolResultBlock(call_id="c1", content="# Tienda\nUna tienda.")],
            ),
            said("Describe una tienda."),
        )
    )

    assert text == (
        "# ¿Qué dice el README?\n"
        "\n"
        "- Session: `20261030-101500-3fa2`, started 2026-10-30 10:15 UTC\n"
        "- Directory: `/home/ana/proyecto`\n"
        "- Model: `glm-5.3-flash` (opencode-go)\n"
        "- Tokens: 1200 in · 80 out · $0.0012\n"
        "\n"
        "## User\n"
        "\n"
        "¿Qué dice el README?\n"
        "En corto.\n"
        "\n"
        "## maha\n"
        "\n"
        "Lo miro.\n"
        "\n"
        "**→ read_file**\n"
        "\n"
        "```json\n"
        '{"path": "README.md"}\n'
        "```\n"
        "\n"
        "**✓ read_file**\n"
        "\n"
        "```\n"
        "# Tienda\n"
        "Una tienda.\n"
        "```\n"
        "\n"
        "Describe una tienda.\n"
    )


def test_a_failed_call_and_an_interrupted_answer_are_marked() -> None:
    call = ToolCallBlock(id="c1", name="write_file", arguments="{}")
    text = markdown(
        session(
            user("Escribe"),
            Message(role="assistant", blocks=[call]),
            Message(
                role="tool",
                blocks=[
                    ToolResultBlock(
                        call_id="c1", content="error: the user denied", is_error=True
                    )
                ],
            ),
            said("Vale, enton", interrupted=True),
        )
    )

    assert "**✗ write_file**\n\n```\nerror: the user denied\n```\n" in text
    assert text.endswith("Vale, enton\n\n_(interrupted)_\n")


def test_a_fence_is_longer_than_any_in_the_content() -> None:
    call = ToolCallBlock(id="c1", name="read_file", arguments="{}")
    text = markdown(
        session(
            user("Lee"),
            Message(role="assistant", blocks=[call]),
            Message(
                role="tool",
                blocks=[ToolResultBlock(call_id="c1", content="```\nx\n````")],
            ),
            said("Hecho."),
        )
    )

    assert "`````\n```\nx\n````\n`````\n" in text


def test_a_long_result_is_cut() -> None:
    call = ToolCallBlock(id="c1", name="read_file", arguments="{}")
    content = "\n".join(f"line {n}" for n in range(1, 101))
    text = markdown(
        session(
            user("Lee"),
            Message(role="assistant", blocks=[call]),
            Message(
                role="tool", blocks=[ToolResultBlock(call_id="c1", content=content)]
            ),
            said("Hecho."),
        )
    )

    assert (
        "line 40\n```\n\n_(60 more lines; maha export --format json has them all)_\n"
        in text
    )
    assert "line 41" not in text


def test_without_a_price_the_cost_is_left_out() -> None:
    text = markdown(
        Session(
            header=HEADER,
            messages=[user("Hola"), said("Hola.")],
            model="local",
            usage=Usage(input_tokens=5, output_tokens=2),
            uncosted_turns=1,
        )
    )

    assert "- Tokens: 5 in · 2 out\n" in text
    assert "- Model: `local` (opencode-go)\n" in text
