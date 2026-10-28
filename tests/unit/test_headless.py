"""`run_once()`: one turn without a person, summed up (spec hito 8, §1.3)."""

from datetime import date
from decimal import Decimal

import pytest

from mharness.application.headless import RunResult, instruction, run_once
from mharness.domain.approval import ApprovalRequest
from mharness.domain.catalog import ModelInfo, Prices
from mharness.domain.errors import ModelUnavailableError
from mharness.domain.messages import ToolCallBlock
from mharness.domain.model import Usage
from tests.fakes.approval import FakeApproval
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import FAKE_MODEL, FakeModelClient, reply, tool_calls
from tests.fakes.sessions import MemorySessionStore
from tests.fakes.tools import FakeTool
from tests.unit.test_sessions import FIRST, World

ASK = ApprovalRequest(tool="echo", title="echo Hola", detail="", scope="echo")


def call(id: str) -> ToolCallBlock:
    return ToolCallBlock(id=id, name="echo", arguments='{"text": "Hola"}')


async def test_the_result_has_the_final_answer_and_the_counts() -> None:
    # The text of the last step only: "Voy a mirar." came before a call.
    usage = Usage(input_tokens=1_000_000, output_tokens=0)
    fake = FakeModelClient(
        [
            tool_calls(call("c1"), text="Voy a mirar.", usage=usage),
            reply("Hay dos ficheros.", usage=usage),
        ]
    )
    priced = ModelInfo(
        provider="opencode-go",
        model=FAKE_MODEL,
        prices=Prices(
            input=Decimal("0.15"), output=Decimal("0.50"), checked=date(2026, 10, 27)
        ),
    )
    world = World(MemorySessionStore(), fake, catalog=MemoryCatalog([priced]))
    conversation = await world.sessions.start()

    result = await run_once(conversation, "¿Qué hay aquí?")

    assert result.model_dump(exclude={"duration"}) == RunResult(
        session=FIRST,
        text="Hay dos ficheros.",
        reason="end_turn",
        steps=2,
        tool_calls=1,
        tool_errors=0,
        denials=[],
        usage=Usage(input_tokens=2_000_000),
        cost=Decimal("0.30"),
        duration=0,
        model=FAKE_MODEL,
        error=None,
    ).model_dump(exclude={"duration"})
    assert result.duration >= 0


async def test_a_denied_call_is_named_and_not_a_tool_error() -> None:
    effect = FakeTool(permission="effect", requests=[ASK])
    fake = FakeModelClient([tool_calls(call("c1"))])
    world = World(
        MemorySessionStore(), fake, tools=[effect], gate=FakeApproval(["deny"])
    )

    result = await run_once(await world.sessions.start(), "Hazlo")

    assert (result.reason, result.denials, result.tool_errors) == (
        "denied",
        ["echo Hola"],
        0,
    )


async def test_tool_errors_are_counted() -> None:
    echo = FakeTool(results=[ValueError("roto")])
    fake = FakeModelClient([tool_calls(call("c1")), reply("Vaya.")])
    world = World(MemorySessionStore(), fake, tools=[echo])

    result = await run_once(await world.sessions.start(), "Hazlo")

    assert (result.reason, result.tool_errors) == ("end_turn", 1)


async def test_a_failed_model_call_is_an_error_result() -> None:
    fake = FakeModelClient([ModelUnavailableError("503 Service Unavailable")])
    world = World(MemorySessionStore(), fake)

    result = await run_once(await world.sessions.start(), "Hola")

    assert (result.reason, result.error) == ("error", "503 Service Unavailable")
    assert result.text == ""


async def test_the_calls_that_ran_count_even_if_the_model_fails_later() -> None:
    fake = FakeModelClient(
        [tool_calls(call("c1")), ModelUnavailableError("503 Service Unavailable")]
    )
    world = World(MemorySessionStore(), fake)

    result = await run_once(await world.sessions.start(), "Hola")

    assert (result.reason, result.steps, result.tool_calls) == ("error", 1, 1)


async def test_on_event_sees_every_event_in_order() -> None:
    fake = FakeModelClient([reply("Hola.")])
    world = World(MemorySessionStore(), fake)
    seen: list[str] = []

    await run_once(
        await world.sessions.start(), "Hola", lambda event: seen.append(event.type)
    )

    assert seen == [
        "turn_started",
        "text_delta",
        "text_delta",
        "model_call_finished",
        "turn_finished",
    ]


# instruction(): what `maha -p` asks (spec hito 8, §1.10).


def test_the_text_alone_is_the_instruction() -> None:
    assert instruction("resume este proyecto", None) == "resume este proyecto"


def test_what_is_piped_goes_below_between_delimiters() -> None:
    assert instruction("revisa este diff", "+ hola\n- adiós\n") == (
        "revisa este diff\n\n<stdin>\n+ hola\n- adiós\n</stdin>"
    )


def test_without_text_what_is_piped_is_the_instruction() -> None:
    assert instruction("", "arregla el test\n") == "arregla el test\n"


@pytest.mark.parametrize("piped", ["", " \n\n"])
def test_nothing_piped_adds_nothing(piped: str) -> None:
    assert instruction("hola", piped) == "hola"
