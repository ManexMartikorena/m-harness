"""`AnthropicClient.stream()`: Anthropic's events as the domain's (spec
hito 9, §1.4), with streams copied from the docs and the real calls of
§1.0, and invented ids."""

import asyncio
import json
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from mharness.adapters.models import anthropic
from mharness.adapters.models.anthropic import AnthropicClient
from mharness.domain.errors import (
    ModelRateLimitError,
    ModelResponseError,
    ModelUnavailableError,
)
from mharness.domain.events import ModelEvent, ReasoningDelta, TextDelta, UsageSoFar
from mharness.domain.messages import Message, ReasoningBlock, TextBlock, ToolCallBlock
from mharness.domain.model import ModelRequest, Usage
from tests.adapters.test_anthropic import (
    API_KEY,
    BASE_URL,
    ENDPOINT,
    MODEL,
    sse,
    user,
)
from tests.fakes.model import collect

REQUEST = ModelRequest(model=MODEL, messages=[user("Hola")])


def event(data: dict[str, Any]) -> str:
    return f"event: {data['type']}\ndata: {json.dumps(data)}\n\n"


START = event(
    {
        "type": "message_start",
        "message": {"model": MODEL, "usage": {"input_tokens": 10, "output_tokens": 1}},
    }
)
STOP = event(
    {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn"},
        "usage": {"input_tokens": 10, "output_tokens": 3},
    }
) + event({"type": "message_stop"})


def stream_of(*parts: str) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content="".join(parts).encode(),
    )


@pytest.fixture
async def client() -> AsyncIterator[AnthropicClient]:
    async with AnthropicClient(base_url=BASE_URL, api_key=API_KEY) as subject:
        yield subject


async def events(client: AnthropicClient) -> list[ModelEvent]:
    return [e async for e in client.stream(REQUEST)]


@respx.mock
async def test_text_usage_and_cache(client: AnthropicClient) -> None:
    respx.post(ENDPOINT).mock(return_value=sse("hello.sse"))

    response = await collect(client.stream(REQUEST))

    assert response.message == Message(
        role="assistant", blocks=[TextBlock(text="Hola, Ane.")]
    )
    assert (response.stop_reason, response.model) == ("end_turn", "claude-haiku-5-5")
    # The whole prompt, as the domain counts it: 4 + 2546 written.
    assert response.usage == Usage(
        input_tokens=2550, output_tokens=6, cache_write_tokens=2546
    )
    assert response.cost is None


@respx.mock
async def test_reasoning_text_and_calls_in_their_order(
    client: AnthropicClient,
) -> None:
    respx.post(ENDPOINT).mock(return_value=sse("tool_with_thinking.sse"))

    response = await collect(client.stream(REQUEST))

    assert response.message.blocks == [
        ReasoningBlock(text="", signature="EqFakeSignature0001"),
        TextBlock(text="Voy a leerlo."),
        ToolCallBlock(
            id="toolu_01Fake0000000001",
            name="read_file",
            arguments='{"path": "notas.txt"}',
        ),
        ReasoningBlock(redacted="EncryptedFake0001"),
        # Without arguments, an empty object (spec hito 9, §1.4).
        ToolCallBlock(id="toolu_01Fake0000000002", name="list_dir", arguments="{}"),
    ]
    assert response.stop_reason == "tool_use"
    assert response.usage.reasoning_tokens == 40


@respx.mock
async def test_the_input_is_told_at_the_start(client: AnthropicClient) -> None:
    # Audit after hito 10 (B2): paid from message_start, even if the answer
    # is cut after it.
    respx.post(ENDPOINT).mock(return_value=stream_of(START, STOP))

    first = (await events(client))[0]

    assert first == UsageSoFar(
        usage=Usage(input_tokens=10, output_tokens=1), model=MODEL
    )


@respx.mock
async def test_the_text_carries_its_block(client: AnthropicClient) -> None:
    respx.post(ENDPOINT).mock(return_value=sse("tool_with_thinking.sse"))

    texts = [e for e in await events(client) if isinstance(e, TextDelta)]

    assert texts == [TextDelta(text="Voy a leerlo.", block=1)]


@respx.mock
async def test_the_cost_opencode_reports_wins(client: AnthropicClient) -> None:
    # Measured on OpenCode Go, 2026-11-03 (spec hito 9, §1.0).
    usage = {
        "input_tokens": 4,
        "output_tokens": 51,
        "cache_read_input_tokens": 2546,
        "cache_creation_input_tokens": 0,
        "cost": 0,
        "opencode": {"list_cost": 0.00005136, "allowance": 0.00020544},
    }
    respx.post(ENDPOINT).mock(
        return_value=stream_of(
            START,
            event(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": usage,
                }
            ),
            event({"type": "message_stop"}),
        )
    )

    response = await collect(client.stream(REQUEST))

    assert response.cost == Decimal("0.00020544")
    assert (response.usage.input_tokens, response.usage.cache_read_tokens) == (
        2550,
        2546,
    )


@respx.mock
@pytest.mark.parametrize(
    ("reason", "stop"),
    [
        ("end_turn", "end_turn"),
        ("tool_use", "tool_use"),
        ("max_tokens", "max_tokens"),
        ("model_context_window_exceeded", "context_full"),
        ("refusal", "content_filter"),
        ("stop_sequence", "other"),
        ("pause_turn", "other"),
        ("algo_nuevo", "other"),
    ],
)
async def test_each_stop_reason(
    client: AnthropicClient, reason: str, stop: str
) -> None:
    respx.post(ENDPOINT).mock(
        return_value=stream_of(
            START,
            event({"type": "message_delta", "delta": {"stop_reason": reason}}),
            event({"type": "message_stop"}),
        )
    )

    assert (await collect(client.stream(REQUEST))).stop_reason == stop


@respx.mock
async def test_a_refusal_without_text_says_why(client: AnthropicClient) -> None:
    # The person must see it (spec hito 5, §1.11).
    details = {"type": "refusal", "category": "cyber", "explanation": "No puedo."}
    respx.post(ENDPOINT).mock(
        return_value=stream_of(
            START,
            event(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "refusal", "stop_details": details},
                }
            ),
            event({"type": "message_stop"}),
        )
    )

    response = await collect(client.stream(REQUEST))

    assert (response.message.text, response.stop_reason) == (
        "No puedo.",
        "content_filter",
    )


@respx.mock
async def test_pings_and_unknown_events_are_ignored(client: AnthropicClient) -> None:
    respx.post(ENDPOINT).mock(
        return_value=stream_of(
            START,
            event({"type": "ping"}),
            event({"type": "evento_nuevo", "algo": 1}),
            event(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "bloque_nuevo"},
                }
            ),
            event(
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {"type": "text", "text": ""},
                }
            ),
            event(
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "text_delta", "text": "Hola."},
                }
            ),
            STOP,
        )
    )

    response = await collect(client.stream(REQUEST))

    assert response.message.text == "Hola."


@respx.mock
@pytest.mark.parametrize(
    ("kind", "error"),
    [
        ("overloaded_error", ModelUnavailableError),
        ("rate_limit_error", ModelRateLimitError),
    ],
)
async def test_an_error_in_the_middle(
    client: AnthropicClient, kind: str, error: type[Exception]
) -> None:
    respx.post(ENDPOINT).mock(
        return_value=stream_of(
            START,
            event(
                {"type": "error", "error": {"type": kind, "message": f"Ups {API_KEY}"}}
            ),
        )
    )

    with pytest.raises(error) as raised:
        await events(client)

    assert "the provider failed while answering: Ups [redacted]" in str(raised.value)


@respx.mock
@pytest.mark.parametrize(
    "parts",
    [
        # Without message_stop.
        [START, event({"type": "message_delta", "delta": {"stop_reason": "end_turn"}})],
        # Without stop_reason.
        [START, event({"type": "message_stop"})],
    ],
)
async def test_a_stream_that_does_not_finish_fails(
    client: AnthropicClient, parts: list[str]
) -> None:
    respx.post(ENDPOINT).mock(return_value=stream_of(*parts))

    with pytest.raises(ModelUnavailableError, match="before the answer was complete"):
        await events(client)


@respx.mock
async def test_an_event_that_is_not_an_object_fails(client: AnthropicClient) -> None:
    respx.post(ENDPOINT).mock(return_value=stream_of(START, "data: [1, 2]\n\n"))

    with pytest.raises(ModelResponseError, match="could not be understood"):
        await events(client)


@respx.mock
async def test_a_200_that_is_not_a_stream_fails(client: AnthropicClient) -> None:
    respx.post(ENDPOINT).respond(
        json={"type": "error", "error": {"type": "api_error", "message": "raro"}}
    )

    with pytest.raises(ModelResponseError, match="raro"):
        await events(client)


async def test_a_provider_that_only_pings_is_cut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pings are no progress (spec hito 9, §1.4).
    monkeypatch.setattr(anthropic, "STALL_SECONDS", 0.2)

    async def pings() -> AsyncIterator[bytes]:
        yield START.encode()
        while True:
            yield event({"type": "ping"}).encode()
            await asyncio.sleep(0.05)

    with respx.mock:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=pings()
            )
        )
        async with AnthropicClient(base_url=BASE_URL, api_key=API_KEY) as subject:
            with pytest.raises(ModelUnavailableError, match=r"sent nothing for 0\.2 s"):
                await collect(subject.stream(REQUEST))


@respx.mock
async def test_the_reasoning_deltas_carry_text_and_signature(
    client: AnthropicClient,
) -> None:
    respx.post(ENDPOINT).mock(
        return_value=stream_of(
            START,
            event(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "thinking", "thinking": ""},
                }
            ),
            event(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "thinking_delta", "thinking": "Pienso."},
                }
            ),
            event(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "signature_delta", "signature": "s"},
                }
            ),
            STOP,
        )
    )

    reasoning = [e for e in await events(client) if isinstance(e, ReasoningDelta)]

    assert [(r.text, r.signature) for r in reasoning] == [
        ("", None),
        ("Pienso.", None),
        ("", "s"),
    ]


@respx.mock
async def test_writes_to_the_hour_cache_are_counted_apart(
    client: AnthropicClient,
) -> None:
    usage = {
        "input_tokens": 4,
        "output_tokens": 5,
        "cache_creation_input_tokens": 3000,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 1000,
            "ephemeral_1h_input_tokens": 2000,
        },
    }
    respx.post(ENDPOINT).mock(
        return_value=stream_of(
            START,
            event(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": usage,
                }
            ),
            event({"type": "message_stop"}),
        )
    )

    response = await collect(client.stream(REQUEST))

    assert (
        response.usage.cache_write_tokens,
        response.usage.cache_write_1h_tokens,
    ) == (
        3000,
        2000,
    )


@respx.mock
async def test_a_null_in_the_last_usage_does_not_wipe_what_came(
    client: AnthropicClient,
) -> None:
    # Deep audit after hito 9: `|=` replaced the counts with null, and the
    # turn's limits saw almost nothing.
    respx.post(ENDPOINT).mock(
        return_value=stream_of(
            event(
                {
                    "type": "message_start",
                    "message": {
                        "model": MODEL,
                        "usage": {
                            "input_tokens": 1000,
                            "cache_read_input_tokens": 5000,
                            "cache_creation_input_tokens": 200,
                            "output_tokens": 1,
                        },
                    },
                }
            ),
            event(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {
                        "input_tokens": None,
                        "cache_read_input_tokens": None,
                        "cache_creation_input_tokens": None,
                        "output_tokens": 7,
                    },
                }
            ),
            event({"type": "message_stop"}),
        )
    )

    usage = (await collect(client.stream(REQUEST))).usage

    assert (usage.input_tokens, usage.cache_read_tokens, usage.output_tokens) == (
        6200,
        5000,
        7,
    )
