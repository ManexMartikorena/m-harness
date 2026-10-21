"""`OpenAIChatClient.stream()` (spec hito 3, §4.4), with respx."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from mharness.adapters.models import OpenAIChatClient
from mharness.domain.errors import (
    ModelAuthError,
    ModelError,
    ModelRateLimitError,
    ModelRequestError,
    ModelResponseError,
    ModelUnavailableError,
)
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


async def pieces(
    body: bytes, size: int, then: Exception | None = None
) -> AsyncIterator[bytes]:
    for start in range(0, len(body), size):
        yield body[start : start + size]
    if then is not None:
        raise then


def serve(
    body: bytes, size: int = CHUNK_SIZE, then: Exception | None = None
) -> respx.Route:
    """Answer with `body` in pieces of `size` bytes; then raise `then`, if any."""
    return respx.post(ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=pieces(body, size, then),
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


# Errors (spec hito 3, §1.8).


@respx.mock
async def test_done_without_finish_reason_fails(client: OpenAIChatClient) -> None:
    serve(sse(chunk("Hola"), usage_chunk(), "[DONE]"))

    with pytest.raises(ModelResponseError, match="before the answer was complete"):
        await events(client)


@respx.mock
async def test_clean_end_without_finish_reason_fails(client: OpenAIChatClient) -> None:
    serve(sse(chunk("Hola")))

    with pytest.raises(ModelResponseError, match="before the answer was complete"):
        await events(client)


@respx.mock
async def test_data_after_done_is_not_read(client: OpenAIChatClient) -> None:
    serve(sse(chunk("Hola", finish_reason="stop"), "[DONE]", "not json"))

    *_, end = await events(client)

    assert isinstance(end, MessageEnd)


def error_body(message: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": "invalid_request_error"}}


@respx.mock
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, ModelAuthError),
        (403, ModelAuthError),
        (429, ModelRateLimitError),
        (400, ModelRequestError),
        (404, ModelRequestError),
        (500, ModelUnavailableError),
        (503, ModelUnavailableError),
    ],
)
async def test_http_errors_before_the_stream(
    client: OpenAIChatClient, status: int, error: type[ModelError]
) -> None:
    respx.post(ENDPOINT).respond(status, json=error_body("Algo falló."))

    with pytest.raises(error, match=f"HTTP {status}: Algo falló."):
        await events(client)


@respx.mock
async def test_measured_unknown_model_is_a_request_error(
    client: OpenAIChatClient,
) -> None:
    # Measured with OpenCode Go (spec §1.7): 400 with type "server_error".
    body = {
        "error": {
            "type": "server_error",
            "message": "Upstream request failed: Model is unavailable.",
        }
    }
    respx.post(ENDPOINT).respond(400, json=body)

    with pytest.raises(ModelRequestError, match="Model is unavailable"):
        await events(client)


@respx.mock
async def test_http_error_message_is_redacted_and_cut(
    client: OpenAIChatClient,
) -> None:
    respx.post(ENDPOINT).respond(401, json=error_body(f"Bad key {API_KEY}" + "x" * 400))

    with pytest.raises(ModelAuthError) as raised:
        await events(client)

    assert API_KEY not in str(raised.value)
    assert "[redacted]" in str(raised.value)
    assert len(str(raised.value)) <= len("HTTP 401: ") + 300


@respx.mock
async def test_json_200_with_a_message(client: OpenAIChatClient) -> None:
    respx.post(ENDPOINT).respond(200, json=error_body(f"No stream for {API_KEY}"))

    with pytest.raises(ModelResponseError, match="No stream for") as raised:
        await events(client)

    assert API_KEY not in str(raised.value)


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, text="<html>Hola</html>"),
    ],
)
async def test_200_that_is_not_a_stream(
    client: OpenAIChatClient, response: httpx.Response
) -> None:
    respx.post(ENDPOINT).mock(return_value=response)

    with pytest.raises(ModelResponseError, match="did not stream"):
        await events(client)


@respx.mock
@pytest.mark.parametrize("data", ["<secret-body>", '{"choices": "<secret-body>"}'])
async def test_unreadable_chunk_is_a_response_error(
    client: OpenAIChatClient, data: str
) -> None:
    serve(sse(chunk("Hola"), data))

    with pytest.raises(ModelResponseError) as raised:
        await events(client)

    assert "secret-body" not in str(raised.value)


@respx.mock
@pytest.mark.parametrize(
    "error",
    [
        {"message": f"Upstream broke near {API_KEY}" + "x" * 400},
        f"Upstream broke near {API_KEY}" + "x" * 400,
    ],
)
async def test_chunk_with_an_error(client: OpenAIChatClient, error: Any) -> None:
    serve(sse(chunk("Hola"), {"error": error}))

    with pytest.raises(ModelUnavailableError, match="Upstream broke") as raised:
        await events(client)

    message = str(raised.value)
    assert API_KEY not in message
    assert len(message) <= len("the provider failed while answering: ") + 300


@respx.mock
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadError("connection reset"),
        httpx.ReadTimeout("silence"),
        httpx.DecodingError("bad gzip"),
    ],
)
async def test_a_cut_fails_even_after_the_finish_reason(
    client: OpenAIChatClient, failure: Exception
) -> None:
    serve(sse(chunk("Hola", finish_reason="stop"), usage_chunk()), then=failure)

    with pytest.raises(ModelUnavailableError):
        await events(client)


@respx.mock
async def test_network_error_does_not_contain_the_key(
    client: OpenAIChatClient,
) -> None:
    serve(sse(chunk("Hola")), then=httpx.ReadError(f"reset with {API_KEY}"))

    with pytest.raises(ModelUnavailableError) as raised:
        await events(client)

    assert API_KEY not in str(raised.value)


# Closing the connection (spec hito 3, §4.4.19).


class HangingBody(httpx.AsyncByteStream):
    """Sends one chunk and then waits forever; remembers if it was closed."""

    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield sse(chunk("Hola"))
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed = True


def serve_hanging() -> HangingBody:
    body = HangingBody()
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=body
        )
    )
    return body


@respx.mock
async def test_closing_the_consumer_closes_the_connection(
    client: OpenAIChatClient,
) -> None:
    body = serve_hanging()

    async with contextlib.aclosing(client.stream(REQUEST)) as stream:
        first = await anext(stream)

    assert first == TextDelta(text="Hola")
    assert body.closed


@respx.mock
async def test_cancelling_closes_the_connection(client: OpenAIChatClient) -> None:
    body = serve_hanging()
    first_arrived = asyncio.Event()

    async def consume() -> None:
        async with contextlib.aclosing(client.stream(REQUEST)) as stream:
            async for _ in stream:
                first_arrived.set()

    task = asyncio.create_task(consume())
    await first_arrived.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert body.closed
