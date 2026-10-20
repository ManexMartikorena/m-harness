import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from mharness.adapters.models import OpenAIChatClient
from mharness.adapters.models.openai_chat import TIMEOUT
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest
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
    assert httpx.Timeout(120.0, connect=10.0) == TIMEOUT
