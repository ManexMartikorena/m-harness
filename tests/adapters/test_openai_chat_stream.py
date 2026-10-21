"""`OpenAIChatClient.stream()` (spec hito 3, §4.4), with respx."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from mharness.adapters.models import OpenAIChatClient
from mharness.domain.events import MessageEnd, ModelEvent, TextDelta
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest, StopReason, Usage

BASE_URL = "https://models.example.test/v1"
ENDPOINT = f"{BASE_URL}/chat/completions"
API_KEY = "sk-test-0000000000000000"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "openai_chat"
MODEL = "glm-5.3-flash"
REQUEST = ModelRequest(
    model=MODEL, messages=[Message(role="user", blocks=[TextBlock(text="Hola")])]
)
# The measured stream splits events between network reads (spec §1.7).
CHUNK_SIZE = 37


def sse(*chunks: dict[str, Any] | str) -> bytes:
    """A stream body: each chunk as one `data:` event."""
    lines = (f"data: {c if isinstance(c, str) else json.dumps(c)}\n\n" for c in chunks)
    return "".join(lines).encode()


def chunk(
    content: str | None = None,
    *,
    finish_reason: str | None = None,
    **delta: Any,
) -> dict[str, Any]:
    if content is not None:
        delta["content"] = content
    return {
        "model": MODEL,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def usage_chunk(prompt: int = 18, completion: int = 31) -> dict[str, Any]:
    return {
        "model": MODEL,
        "choices": [],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


async def pieces(body: bytes, size: int) -> AsyncIterator[bytes]:
    for start in range(0, len(body), size):
        yield body[start : start + size]


def serve(body: bytes, size: int = CHUNK_SIZE) -> respx.Route:
    """Answer the endpoint with `body`, sent in pieces of `size` bytes."""
    return respx.post(ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=pieces(body, size),
        )
    )


def sent_json(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


async def events(
    client: OpenAIChatClient, request: ModelRequest = REQUEST
) -> list[ModelEvent]:
    return [event async for event in client.stream(request)]


@pytest.fixture
async def client() -> AsyncIterator[OpenAIChatClient]:
    async with OpenAIChatClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        session_header="x-opencode-session",
        session_id="session-1",
    ) as client:
        yield client


@respx.mock
@pytest.mark.parametrize("system", [None, "Eres breve."])
async def test_asks_for_a_stream_with_usage(
    client: OpenAIChatClient, system: str | None
) -> None:
    # Fixes decision 1.11.
    route = serve(sse(chunk("Hola", finish_reason="stop"), "[DONE]"))
    request = ModelRequest(model=MODEL, system=system, messages=REQUEST.messages)

    await events(client, request)

    system_message = [{"role": "system", "content": system}] if system else []
    assert sent_json(route) == {
        "model": MODEL,
        "messages": [*system_message, {"role": "user", "content": "Hola"}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }


@respx.mock
async def test_sends_key_user_agent_and_session(client: OpenAIChatClient) -> None:
    route = serve(sse(chunk("Hola", finish_reason="stop"), "[DONE]"))

    await events(client)

    headers = route.calls.last.request.headers
    assert headers["Authorization"] == f"Bearer {API_KEY}"
    assert headers["User-Agent"].startswith("maha/")
    assert headers["x-opencode-session"] == "session-1"


@respx.mock
async def test_without_key_there_is_no_authorization() -> None:
    route = serve(sse(chunk("Hola", finish_reason="stop"), "[DONE]"))

    async with OpenAIChatClient(base_url=BASE_URL) as client:
        await events(client)

    assert "Authorization" not in route.calls.last.request.headers


@respx.mock
@pytest.mark.parametrize(
    "name", ["stream_finish_with_content.sse", "stream_finish_alone.sse"]
)
async def test_translates_a_measured_stream(
    client: OpenAIChatClient, name: str
) -> None:
    # The finish reason comes with the last text or in a chunk of its own; the
    # usage comes after it, and MessageEnd carries both (decision 1.4).
    serve((FIXTURES / name).read_bytes())

    assert await events(client) == [
        TextDelta(text="Hola, "),
        TextDelta(text="Ane."),
        MessageEnd(
            stop_reason="end_turn",
            usage=Usage(input_tokens=18, output_tokens=31, cache_read_tokens=4),
            model=MODEL,
        ),
    ]


@respx.mock
async def test_only_content_becomes_text(client: OpenAIChatClient) -> None:
    serve(
        sse(
            chunk("", role="assistant"),
            chunk(reasoning_content="Pienso."),
            chunk(None),
            chunk("Hola", obfuscation="xyz", unknown={"a": 1}),
            chunk(finish_reason="stop"),
            usage_chunk(),
            "[DONE]",
        )
    )

    texts = [e.text for e in await events(client) if isinstance(e, TextDelta)]

    assert texts == ["Hola"]


@respx.mock
async def test_without_usage_or_model(client: OpenAIChatClient) -> None:
    serve(sse({"choices": [{"delta": {"content": "Hola"}, "finish_reason": "stop"}]}))

    *_, end = await events(client)

    assert end == MessageEnd(stop_reason="end_turn", usage=Usage(), model=MODEL)


@respx.mock
@pytest.mark.parametrize(
    ("finish_reason", "stop_reason"),
    [
        ("stop", "end_turn"),
        ("length", "max_tokens"),
        ("tool_calls", "tool_use"),
        ("content_filter", "content_filter"),
        ("something_new", "other"),
    ],
)
async def test_translates_each_finish_reason(
    client: OpenAIChatClient, finish_reason: str, stop_reason: StopReason
) -> None:
    serve(sse(chunk("Hola", finish_reason=finish_reason), "[DONE]"))

    *_, end = await events(client)

    assert isinstance(end, MessageEnd)
    assert end.stop_reason == stop_reason


@respx.mock
async def test_bom_and_split_characters(client: OpenAIChatClient) -> None:
    # One byte per piece: "ñ" and "€" arrive split between pieces.
    body = b"\xef\xbb\xbf" + sse(chunk("Año: 5 €", finish_reason="stop"), "[DONE]")
    serve(body, size=1)

    first, *_ = await events(client)

    assert first == TextDelta(text="Año: 5 €")
