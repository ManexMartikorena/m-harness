"""`AnthropicClient`: the request in the Messages API format, `complete()`
and the HTTP errors (spec hito 9, §1.3, §1.9 and §1.10)."""

import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from mharness.adapters.models.anthropic import (
    DEFAULT_MAX_TOKENS,
    VERSION,
    AnthropicClient,
)
from mharness.domain.errors import (
    ModelAuthError,
    ModelError,
    ModelRateLimitError,
    ModelRequestError,
    ModelResponseError,
    ModelUnavailableError,
    RetryableModelError,
)
from mharness.domain.messages import (
    Message,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from mharness.domain.model import ModelRequest, ToolSpec, Usage
from mharness.ports.model import ModelClient
from tests.fakes.model import collect

BASE_URL = "https://claude.example.test/v1"
ENDPOINT = f"{BASE_URL}/messages"
API_KEY = "sk-ant-test-0000000000000000"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "anthropic"
MODEL = "claude-haiku-5-5"


def sse(name: str = "hello.sse") -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=(FIXTURES / name).read_bytes(),
    )


def sent(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


def user(text: str) -> Message:
    return Message(role="user", blocks=[TextBlock(text=text)])


@pytest.fixture
async def client() -> AsyncIterator[AnthropicClient]:
    async with AnthropicClient(base_url=BASE_URL, api_key=API_KEY) as subject:
        yield subject


async def ask(client: AnthropicClient, request: ModelRequest) -> Any:
    route = respx.post(ENDPOINT).mock(return_value=sse())
    await collect(client.stream(request))
    return sent(route)


async def test_client_satisfies_the_port() -> None:
    async with AnthropicClient(base_url=BASE_URL, api_key=API_KEY) as subject:
        port: ModelClient = subject
        assert port is subject


# The request (spec hito 9, §1.3).


@respx.mock
async def test_the_simplest_request(client: AnthropicClient) -> None:
    body = await ask(client, ModelRequest(model=MODEL, messages=[user("Hola")]))

    assert body == {
        "model": MODEL,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Hola"}]}],
        "cache_control": {"type": "ephemeral"},
        "stream": True,
    }


@respx.mock
async def test_system_tools_max_tokens_and_effort(client: AnthropicClient) -> None:
    schema = {"type": "object", "properties": {"path": {"type": "string"}}}
    request = ModelRequest(
        model=MODEL,
        system="Eres maha.",
        messages=[user("Hola")],
        tools=[ToolSpec(name="read_file", description="Lee.", input_schema=schema)],
        max_tokens=128_000,
        effort="high",
    )

    body = await ask(client, request)

    assert body["system"] == "Eres maha."
    assert body["tools"] == [
        {"name": "read_file", "description": "Lee.", "input_schema": schema}
    ]
    assert (body["max_tokens"], body["output_config"]) == (
        128_000,
        {"effort": "high"},
    )


@respx.mock
async def test_a_tool_turn_in_the_messages_api_format(
    client: AnthropicClient,
) -> None:
    call = ToolCallBlock(id="toolu_1", name="read_file", arguments='{"path": "a"}')
    request = ModelRequest(
        model=MODEL,
        messages=[
            user("Lee a"),
            Message(
                role="assistant",
                blocks=[
                    ReasoningBlock(text="", signature="firma"),
                    TextBlock(text="Voy."),
                    call,
                ],
            ),
            Message(
                role="tool",
                blocks=[ToolResultBlock(call_id="toolu_1", content="uno\ndos")],
            ),
        ],
    )

    body = await ask(client, request)

    assert body["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Lee a"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "firma"},
                {"type": "text", "text": "Voy."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "read_file",
                    "input": {"path": "a"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "uno\ndos"}
            ],
        },
    ]


@respx.mock
async def test_results_and_the_next_words_go_in_one_user_message(
    client: AnthropicClient,
) -> None:
    # After a denial the person writes next: results first, then the text.
    call = ToolCallBlock(id="t1", name="write_file", arguments="{}")
    request = ModelRequest(
        model=MODEL,
        messages=[
            user("Escribe"),
            Message(role="assistant", blocks=[call]),
            Message(
                role="tool",
                blocks=[ToolResultBlock(call_id="t1", content="denied", is_error=True)],
            ),
            user("Déjalo"),
        ],
    )

    body = await ask(client, request)

    assert body["messages"][2] == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": "denied",
                "is_error": True,
            },
            {"type": "text", "text": "Déjalo"},
        ],
    }


@respx.mock
@pytest.mark.parametrize("arguments", ["", "{rota", "[1, 2]", '"texto"'])
async def test_arguments_that_are_not_an_object_go_as_an_empty_one(
    client: AnthropicClient, arguments: str
) -> None:
    # Their error is already in the result that follows (spec hito 4, §1.8).
    call = ToolCallBlock(id="t1", name="read_file", arguments=arguments)
    request = ModelRequest(
        model=MODEL, messages=[user("Lee"), Message(role="assistant", blocks=[call])]
    )

    body = await ask(client, request)

    assert body["messages"][1]["content"][0]["input"] == {}


@respx.mock
async def test_what_cannot_go_back_stays_out(client: AnthropicClient) -> None:
    # A reasoning block cut before its signature, and empty text, would be
    # rejected; a redacted one goes as it came.
    request = ModelRequest(
        model=MODEL,
        messages=[
            user("Hola"),
            Message(
                role="assistant",
                blocks=[
                    ReasoningBlock(text="a medias"),
                    TextBlock(text=""),
                    ReasoningBlock(redacted="cifrado"),
                    TextBlock(text="Hola."),
                ],
            ),
            user("Sigue"),
        ],
    )

    body = await ask(client, request)

    assert body["messages"][1]["content"] == [
        {"type": "redacted_thinking", "data": "cifrado"},
        {"type": "text", "text": "Hola."},
    ]


@respx.mock
async def test_an_interrupted_answer_carries_the_mark(
    client: AnthropicClient,
) -> None:
    # The model knows it did not finish (spec hito 6, §1.7).
    cut = Message(
        role="assistant", blocks=[TextBlock(text="La capital es")], interrupted=True
    )
    request = ModelRequest(
        model=MODEL, messages=[user("¿Capital?"), cut, user("Sigue")]
    )

    body = await ask(client, request)

    assert body["messages"][1]["content"] == [
        {"type": "text", "text": "La capital es"},
        {"type": "text", "text": "[interrupted by the user]"},
    ]


@respx.mock
async def test_headers_key_version_agent_and_session() -> None:
    route = respx.post(ENDPOINT).mock(return_value=sse())
    async with AnthropicClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        session_header="x-opencode-session",
        session_id="sesion-1",
    ) as subject:
        await collect(subject.stream(ModelRequest(model=MODEL, messages=[user("a")])))

    headers = route.calls.last.request.headers
    assert headers["authorization"] == f"Bearer {API_KEY}"
    assert headers["anthropic-version"] == VERSION == "2026-10-21"
    assert headers["user-agent"].startswith("maha/")
    assert headers["x-opencode-session"] == "sesion-1"


@respx.mock
async def test_a_provider_may_ask_for_another_version_and_a_longer_cache() -> None:
    # Spec hito 9, decisions 2 and 9.
    route = respx.post(ENDPOINT).mock(return_value=sse())
    async with AnthropicClient(
        base_url=BASE_URL, api_key=API_KEY, version="2023-06-01", cache_ttl="1h"
    ) as subject:
        await collect(subject.stream(ModelRequest(model=MODEL, messages=[user("a")])))

    assert route.calls.last.request.headers["anthropic-version"] == "2023-06-01"
    assert sent(route)["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


@respx.mock
async def test_without_key_there_is_no_authorization() -> None:
    route = respx.post(ENDPOINT).mock(return_value=sse())
    async with AnthropicClient(base_url=BASE_URL) as subject:
        await collect(subject.stream(ModelRequest(model=MODEL, messages=[user("a")])))

    assert "authorization" not in route.calls.last.request.headers


# HTTP errors (spec hito 9, §1.9).


def error(status: int, message: str, **headers: str) -> httpx.Response:
    body = {"type": "error", "error": {"type": "x", "message": message}}
    return httpx.Response(status, json=body, headers=headers)


@respx.mock
@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, ModelRequestError),
        (401, ModelAuthError),
        (402, ModelRequestError),
        (403, ModelAuthError),
        (404, ModelRequestError),
        # Deep audit after hito 9 (M8): it can pass, as the SDKs retry it.
        (408, ModelUnavailableError),
        (413, ModelRequestError),
        (429, ModelRateLimitError),
        (500, ModelUnavailableError),
        (504, ModelUnavailableError),
        (529, ModelUnavailableError),
    ],
)
async def test_each_http_error(
    client: AnthropicClient, status: int, kind: type[ModelError]
) -> None:
    respx.post(ENDPOINT).mock(return_value=error(status, f"mal: {API_KEY}"))
    request = ModelRequest(model=MODEL, messages=[user("a")])

    with pytest.raises(kind) as raised:
        await collect(client.stream(request))

    assert str(raised.value) == f"HTTP {status}: mal: [redacted]"


@respx.mock
@pytest.mark.parametrize("status", [429, 529])
async def test_retry_after_reaches_the_error(
    client: AnthropicClient, status: int
) -> None:
    respx.post(ENDPOINT).mock(
        return_value=error(status, "espera", **{"retry-after": "7"})
    )

    with pytest.raises(RetryableModelError) as raised:
        await client.complete(ModelRequest(model=MODEL, messages=[user("a")]))

    assert raised.value.retry_after == 7.0


@respx.mock
async def test_a_network_failure_is_unavailable(client: AnthropicClient) -> None:
    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError(f"no {API_KEY}"))

    with pytest.raises(ModelUnavailableError) as raised:
        await collect(client.stream(ModelRequest(model=MODEL, messages=[user("a")])))

    assert API_KEY not in str(raised.value)


# complete() (spec hito 9, §1.10).


@respx.mock
async def test_complete_translates_the_whole_answer(client: AnthropicClient) -> None:
    route = respx.post(ENDPOINT).respond(
        json={
            "id": "msg_01Fake",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "s"},
                {"type": "text", "text": "Lo leo."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "read_file",
                    "input": {"path": "ñ.txt"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {
                "input_tokens": 3,
                "output_tokens": 20,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 0,
            },
        }
    )

    response = await client.complete(ModelRequest(model=MODEL, messages=[user("a")]))

    assert "stream" not in sent(route)
    assert response.message.blocks == [
        ReasoningBlock(signature="s"),
        TextBlock(text="Lo leo."),
        ToolCallBlock(id="toolu_1", name="read_file", arguments='{"path": "ñ.txt"}'),
    ]
    assert (response.stop_reason, response.model) == ("tool_use", "claude-opus-5-5")
    assert response.usage == Usage(
        input_tokens=103, output_tokens=20, cache_read_tokens=100
    )


@respx.mock
async def test_complete_with_a_refusal_says_why(client: AnthropicClient) -> None:
    respx.post(ENDPOINT).respond(
        json={
            "model": MODEL,
            "content": [],
            "stop_reason": "refusal",
            "stop_details": {"explanation": "No puedo."},
            "usage": {},
        }
    )

    response = await client.complete(ModelRequest(model=MODEL, messages=[user("a")]))

    assert (response.message.text, response.stop_reason) == (
        "No puedo.",
        "content_filter",
    )


@respx.mock
@pytest.mark.parametrize("body", [b"no es json", b"[]", b'{"content": "x"}'])
async def test_complete_with_a_body_it_cannot_read(
    client: AnthropicClient, body: bytes
) -> None:
    respx.post(ENDPOINT).respond(200, content=body)

    with pytest.raises(ModelResponseError, match="could not be understood"):
        await client.complete(ModelRequest(model=MODEL, messages=[user("a")]))


@respx.mock
async def test_ids_anthropic_would_refuse_go_remade_the_same_on_both_sides(
    client: AnthropicClient,
) -> None:
    # Deep audit after hito 9 (M2): Anthropic asks ^[a-zA-Z0-9_-]+$ for a
    # tool_use id; a call made by another server (functions.read_file:0)
    # broke every request after /model.
    odd = "functions.read_file:0"
    other = "functions.read_file:1"
    request = ModelRequest(
        model=MODEL,
        messages=[
            user("Lee"),
            Message(
                role="assistant",
                blocks=[
                    ToolCallBlock(id=odd, name="read_file", arguments="{}"),
                    ToolCallBlock(id=other, name="read_file", arguments="{}"),
                    ToolCallBlock(id="toolu_ok-1", name="read_file", arguments="{}"),
                ],
            ),
            Message(
                role="tool",
                blocks=[
                    ToolResultBlock(call_id=odd, content="a"),
                    ToolResultBlock(call_id=other, content="b"),
                    ToolResultBlock(call_id="toolu_ok-1", content="c"),
                ],
            ),
        ],
    )

    body = await ask(client, request)

    uses = [b["id"] for b in body["messages"][1]["content"]]
    results = [b["tool_use_id"] for b in body["messages"][2]["content"]]
    assert uses == results
    assert uses[2] == "toolu_ok-1"
    assert len(set(uses)) == 3
    assert all(re.fullmatch(r"[a-zA-Z0-9_-]+", id_) for id_ in uses)


@respx.mock
async def test_text_of_only_spaces_stays_out(client: AnthropicClient) -> None:
    # Deep audit after hito 9 (M3): the API refuses a text block without
    # visible text; another model, or a cut answer, may leave "\n\n".
    call = ToolCallBlock(id="t1", name="read_file", arguments="{}")
    request = ModelRequest(
        model=MODEL,
        messages=[
            user("Lee"),
            Message(role="assistant", blocks=[TextBlock(text="\n\n"), call]),
            Message(role="tool", blocks=[ToolResultBlock(call_id="t1", content="x")]),
            Message(role="assistant", blocks=[TextBlock(text=" \n")], interrupted=True),
            user("Sigue"),
        ],
    )

    body = await ask(client, request)

    assert body["messages"][1]["content"] == [
        {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}}
    ]
    assert body["messages"][3] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "[interrupted by the user]"}],
    }


@respx.mock
async def test_complete_keeps_no_empty_signature(client: AnthropicClient) -> None:
    # Deep audit after hito 9 (M10): the stream drops "", complete() kept it
    # and would send it back.
    respx.post(ENDPOINT).respond(
        json={
            "model": MODEL,
            "content": [
                {"type": "thinking", "thinking": "", "signature": ""},
                {"type": "text", "text": "Hola."},
            ],
            "stop_reason": "end_turn",
            "usage": {},
        }
    )

    response = await client.complete(ModelRequest(model=MODEL, messages=[user("a")]))

    assert response.message.blocks[0] == ReasoningBlock(signature=None)
