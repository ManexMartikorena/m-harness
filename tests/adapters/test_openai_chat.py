import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from mharness.adapters.models import OpenAIChatClient
from mharness.adapters.models.openai_chat import TIMEOUT
from mharness.domain.errors import (
    ModelAuthError,
    ModelError,
    ModelRateLimitError,
    ModelRequestError,
    ModelResponseError,
    ModelUnavailableError,
)
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import ModelRequest, StopReason, ToolSpec, Usage
from mharness.ports.model import ModelClient

BASE_URL = "https://models.example.test/v1"
ENDPOINT = f"{BASE_URL}/chat/completions"
API_KEY = "sk-test-0000000000000000"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "openai_chat"

CONVERSATION = [
    Message(role="user", blocks=[TextBlock(text="Hola, soy Ane")]),
    Message(role="assistant", blocks=[TextBlock(text="Hola, Ane.")]),
    Message(role="user", blocks=[TextBlock(text="¿Cómo me llamo?")]),
]


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def sent_json(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


@pytest.fixture
async def client() -> AsyncIterator[OpenAIChatClient]:
    async with OpenAIChatClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        session_header="x-opencode-session",
        session_id="session-1",
    ) as client:
        yield client


async def test_client_satisfies_the_port() -> None:
    async with OpenAIChatClient(base_url=BASE_URL) as client:
        # mypy checks this assignment against the Protocol.
        port: ModelClient = client

        assert port is client


@respx.mock
async def test_sends_the_conversation_in_openai_format(
    client: OpenAIChatClient,
) -> None:
    route = respx.post(ENDPOINT).respond(json=fixture("completion.json"))

    await client.complete(ModelRequest(model="glm-5.3-flash", messages=CONVERSATION))

    assert sent_json(route) == {
        "model": "glm-5.3-flash",
        "messages": [
            {"role": "user", "content": "Hola, soy Ane"},
            {"role": "assistant", "content": "Hola, Ane."},
            {"role": "user", "content": "¿Cómo me llamo?"},
        ],
    }


@respx.mock
async def test_system_goes_first_as_a_message(client: OpenAIChatClient) -> None:
    route = respx.post(ENDPOINT).respond(json=fixture("completion.json"))

    await client.complete(
        ModelRequest(
            model="glm-5.3-flash",
            system="Responde en una línea.",
            messages=CONVERSATION[:1],
        )
    )

    assert sent_json(route)["messages"] == [
        {"role": "system", "content": "Responde en una línea."},
        {"role": "user", "content": "Hola, soy Ane"},
    ]


@respx.mock
async def test_text_blocks_are_joined_with_a_newline(client: OpenAIChatClient) -> None:
    route = respx.post(ENDPOINT).respond(json=fixture("completion.json"))
    message = Message(
        role="user", blocks=[TextBlock(text="Uno"), TextBlock(text="Dos")]
    )

    await client.complete(ModelRequest(model="glm-5.3-flash", messages=[message]))

    assert sent_json(route)["messages"] == [{"role": "user", "content": "Uno\nDos"}]


@respx.mock
async def test_sends_key_user_agent_and_session(client: OpenAIChatClient) -> None:
    route = respx.post(ENDPOINT).respond(json=fixture("completion.json"))

    await client.complete(ModelRequest(model="glm-5.3-flash", messages=CONVERSATION))

    headers = route.calls.last.request.headers
    assert headers["Authorization"] == f"Bearer {API_KEY}"
    assert headers["User-Agent"].startswith("maha/")
    assert headers["User-Agent"].endswith(
        "(+https://github.com/ManexMartikorena/m-harness)"
    )
    assert headers["x-opencode-session"] == "session-1"


@respx.mock
async def test_without_key_there_is_no_authorization() -> None:
    route = respx.post(ENDPOINT).respond(json=fixture("completion.json"))

    async with OpenAIChatClient(base_url=BASE_URL) as client:
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    headers = route.calls.last.request.headers
    assert "Authorization" not in headers
    assert "x-opencode-session" not in headers


@respx.mock
async def test_session_id_is_stable_across_calls() -> None:
    route = respx.post(ENDPOINT).respond(json=fixture("completion.json"))
    request = ModelRequest(model="m", messages=CONVERSATION)

    async with OpenAIChatClient(
        base_url=BASE_URL, session_header="x-opencode-session"
    ) as client:
        await client.complete(request)
        await client.complete(request)

    first, second = (call.request.headers["x-opencode-session"] for call in route.calls)
    assert first == second
    assert first


async def test_closing_closes_the_http_client() -> None:
    async with OpenAIChatClient(base_url=BASE_URL) as client:
        pass

    with pytest.raises(RuntimeError):
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))


def test_timeouts() -> None:
    # `read` bounds the silence between chunks, not the whole answer.
    assert httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0) == TIMEOUT


@respx.mock
async def test_translates_the_response(client: OpenAIChatClient) -> None:
    respx.post(ENDPOINT).respond(json=fixture("completion.json"))

    response = await client.complete(
        ModelRequest(model="glm-5.3-flash", messages=CONVERSATION)
    )

    assert response.message == Message(
        role="assistant", blocks=[TextBlock(text="Te llamas Ane.")]
    )
    assert response.stop_reason == "end_turn"
    assert response.usage == Usage(
        input_tokens=31, output_tokens=5, cache_read_tokens=12
    )
    assert response.model == "glm-5.3-flash"


@pytest.mark.parametrize(
    ("finish_reason", "stop_reason"),
    [
        ("stop", "end_turn"),
        ("length", "max_tokens"),
        ("tool_calls", "tool_use"),
        ("content_filter", "content_filter"),
        ("something_new", "other"),
        (None, "other"),
    ],
)
@respx.mock
async def test_translates_each_finish_reason(
    client: OpenAIChatClient, finish_reason: str | None, stop_reason: StopReason
) -> None:
    body = fixture("completion.json")
    body["choices"][0]["finish_reason"] = finish_reason
    respx.post(ENDPOINT).respond(json=body)

    response = await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert response.stop_reason == stop_reason


@respx.mock
async def test_usage_without_cached_tokens(client: OpenAIChatClient) -> None:
    body = fixture("completion.json")
    del body["usage"]["prompt_tokens_details"]
    respx.post(ENDPOINT).respond(json=body)

    response = await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert response.usage == Usage(input_tokens=31, output_tokens=5)


@respx.mock
async def test_usage_with_null_counters(client: OpenAIChatClient) -> None:
    body = fixture("completion.json")
    body["usage"] = {
        "prompt_tokens": 31,
        "completion_tokens": None,
        "prompt_tokens_details": {"cached_tokens": None},
    }
    respx.post(ENDPOINT).respond(json=body)

    response = await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert response.usage == Usage(input_tokens=31)


@respx.mock
async def test_without_usage_tokens_are_zero(client: OpenAIChatClient) -> None:
    body = fixture("completion.json")
    del body["usage"]
    respx.post(ENDPOINT).respond(json=body)

    response = await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert response.usage == Usage()


@respx.mock
async def test_reasoning_and_unknown_fields_are_ignored(
    client: OpenAIChatClient,
) -> None:
    respx.post(ENDPOINT).respond(json=fixture("completion_with_reasoning.json"))

    response = await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert response.message.text == "Te llamas Ane."


@respx.mock
async def test_null_content_gives_an_empty_message(client: OpenAIChatClient) -> None:
    body = fixture("completion.json")
    body["choices"][0]["message"]["content"] = None
    respx.post(ENDPOINT).respond(json=body)

    response = await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert response.message == Message(role="assistant", blocks=[])


@respx.mock
async def test_without_model_uses_the_requested_one(client: OpenAIChatClient) -> None:
    body = fixture("completion.json")
    del body["model"]
    respx.post(ENDPOINT).respond(json=body)

    response = await client.complete(
        ModelRequest(model="glm-5.3-flash", messages=CONVERSATION)
    )

    assert response.model == "glm-5.3-flash"


def error_body(message: str) -> dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": "invalid_request_error",
            "param": None,
            "code": None,
        }
    }


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, ModelRequestError),
        (401, ModelAuthError),
        (403, ModelAuthError),
        (404, ModelRequestError),
        (429, ModelRateLimitError),
        (500, ModelUnavailableError),
        (503, ModelUnavailableError),
    ],
)
@respx.mock
async def test_http_errors_become_model_errors(
    client: OpenAIChatClient, status: int, error: type[ModelError]
) -> None:
    respx.post(ENDPOINT).respond(status, json=error_body("Something failed"))

    with pytest.raises(error) as raised:
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert str(raised.value) == f"HTTP {status}: Something failed"


@respx.mock
async def test_long_provider_message_is_cut(client: OpenAIChatClient) -> None:
    respx.post(ENDPOINT).respond(400, json=error_body("x" * 1000))

    with pytest.raises(ModelRequestError) as raised:
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert str(raised.value) == "HTTP 400: " + "x" * 300


@pytest.mark.parametrize(
    "body",
    [b"<html>Bad Gateway</html>", b"{}", b'{"error": {"code": 1}}', b"[]", b""],
)
@respx.mock
async def test_error_without_a_message_uses_the_status(
    client: OpenAIChatClient, body: bytes
) -> None:
    respx.post(ENDPOINT).respond(502, content=body)

    with pytest.raises(ModelUnavailableError) as raised:
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert str(raised.value) == "HTTP 502"


@respx.mock
async def test_error_as_a_plain_string(client: OpenAIChatClient) -> None:
    respx.post(ENDPOINT).respond(404, json={"error": "Model not found"})

    with pytest.raises(ModelRequestError, match="HTTP 404: Model not found"):
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))


@pytest.mark.parametrize(
    "exception",
    [
        httpx.ConnectTimeout("connect timed out"),
        httpx.ReadTimeout("read timed out"),
        httpx.ConnectError("Name or service not known"),
        httpx.RemoteProtocolError("Server disconnected"),
        # Not transport errors, but request errors all the same (spec
        # mejora-2026-10-23-deuda-hito-5, A7).
        httpx.DecodingError("bad gzip"),
        httpx.TooManyRedirects("too many"),
    ],
)
@respx.mock
async def test_network_failures_are_unavailable(
    client: OpenAIChatClient, exception: Exception
) -> None:
    respx.post(ENDPOINT).mock(side_effect=exception)

    with pytest.raises(ModelUnavailableError):
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))


@pytest.mark.parametrize(
    "content",
    [b"{not json", b'{"model": "m"}', b'{"choices": []}', b'{"choices": [{}]}'],
)
@respx.mock
async def test_unreadable_200_is_a_response_error(
    client: OpenAIChatClient, content: bytes
) -> None:
    respx.post(ENDPOINT).respond(200, content=content)

    with pytest.raises(ModelResponseError):
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))


@pytest.mark.parametrize("status", [401, 400, 500])
@respx.mock
async def test_no_error_contains_the_key(client: OpenAIChatClient, status: int) -> None:
    # A provider that echoes the key back in its error message.
    respx.post(ENDPOINT).respond(status, json=error_body(f"Invalid key: {API_KEY}"))

    with pytest.raises(ModelError) as raised:
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert API_KEY not in str(raised.value)
    assert "[redacted]" in str(raised.value)


@respx.mock
async def test_network_error_does_not_contain_the_key(
    client: OpenAIChatClient,
) -> None:
    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ModelUnavailableError) as raised:
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert API_KEY not in str(raised.value)


@respx.mock
async def test_key_cut_by_the_limit_is_not_shown(client: OpenAIChatClient) -> None:
    # The key straddles the 300-character cut: no piece of it may remain.
    message = "x" * 290 + API_KEY
    respx.post(ENDPOINT).respond(401, json=error_body(message))

    with pytest.raises(ModelAuthError) as raised:
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert API_KEY[:10] not in str(raised.value)


# Tools and their results (spec hito 4, §1.4).

READ_FILE = ToolSpec(
    name="read_file",
    description="Read a text file.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
)


@respx.mock
async def test_sends_the_tools(client: OpenAIChatClient) -> None:
    route = respx.post(ENDPOINT).respond(json=fixture("completion.json"))

    await client.complete(
        ModelRequest(model="m", messages=CONVERSATION, tools=[READ_FILE])
    )

    assert sent_json(route)["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a text file.",
                "parameters": READ_FILE.input_schema,
            },
        }
    ]


@respx.mock
async def test_without_tools_there_is_no_tools_key(client: OpenAIChatClient) -> None:
    route = respx.post(ENDPOINT).respond(json=fixture("completion.json"))

    await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert "tools" not in sent_json(route)


@respx.mock
async def test_sends_calls_and_results_in_openai_format(
    client: OpenAIChatClient,
) -> None:
    route = respx.post(ENDPOINT).respond(json=fixture("completion.json"))
    call_a = ToolCallBlock(id="call_a", name="read_file", arguments='{"path": "a.txt"}')
    call_b = ToolCallBlock(id="call_b", name="read_file", arguments='{"path": ')
    history = [
        Message(role="user", blocks=[TextBlock(text="Lee a.txt y b.txt")]),
        Message(role="assistant", blocks=[call_a, call_b]),
        Message(
            role="tool",
            blocks=[
                ToolResultBlock(call_id="call_a", content="     1\tHola"),
                ToolResultBlock(
                    call_id="call_b",
                    content="error: arguments are not a valid JSON object",
                    is_error=True,
                ),
            ],
        ),
        Message(
            role="assistant",
            blocks=[
                TextBlock(text="Leo otra vez:"),
                ToolCallBlock(id="call_c", name="list_dir", arguments="{}"),
            ],
        ),
    ]

    await client.complete(ModelRequest(model="m", messages=history))

    assert sent_json(route)["messages"] == [
        {"role": "user", "content": "Lee a.txt y b.txt"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_a",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'},
                },
                {
                    "id": "call_b",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": '},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_a", "content": "     1\tHola"},
        {
            "role": "tool",
            "tool_call_id": "call_b",
            "content": "error: arguments are not a valid JSON object",
        },
        {
            "role": "assistant",
            "content": "Leo otra vez:",
            "tool_calls": [
                {
                    "id": "call_c",
                    "type": "function",
                    "function": {"name": "list_dir", "arguments": "{}"},
                }
            ],
        },
    ]


@respx.mock
async def test_translates_tool_calls_of_a_whole_response(
    client: OpenAIChatClient,
) -> None:
    # Shape measured on OpenCode Go (spec hito 4, §1.1): content "" and the
    # calls in message.tool_calls.
    respx.post(ENDPOINT).respond(json=fixture("completion_with_tool_calls.json"))

    response = await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert response.stop_reason == "tool_use"
    assert response.message.blocks == [
        ToolCallBlock(
            id="call_test_000000000000000c",
            name="read_file",
            arguments='{"path": "notas.txt"}',
        )
    ]


@respx.mock
async def test_a_network_failure_never_shows_the_key(client: OpenAIChatClient) -> None:
    # As stream() already does (spec mejora-2026-10-23-deuda-hito-5, A7).
    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError(f"refused {API_KEY}"))

    with pytest.raises(ModelUnavailableError) as error:
        await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert API_KEY not in str(error.value)
    assert "[redacted]" in str(error.value)


@respx.mock
async def test_a_refusal_comes_as_text(client: OpenAIChatClient) -> None:
    # OpenAI sends it in `refusal`, not in `content`; lost before (spec hito
    # 5, §1.11).
    respx.post(ENDPOINT).respond(
        json={
            "model": "m",
            "choices": [
                {
                    "message": {"content": None, "refusal": "No puedo ayudar."},
                    "finish_reason": "stop",
                }
            ],
        }
    )

    response = await client.complete(ModelRequest(model="m", messages=CONVERSATION))

    assert response.message.text == "No puedo ayudar."
