"""Adapter for the OpenAI Chat Completions format (spec hito 2, §1.8).

Translates between the domain types and the JSON of any server that speaks
this format: OpenCode Go, OpenCode Zen, OpenRouter, Ollama… It decides nothing
about the agent.
"""

import uuid
from importlib.metadata import version
from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import BaseModel

from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest, ModelResponse, Usage

USER_AGENT = (
    f"maha/{version('m-harness')} (+https://github.com/ManexMartikorena/m-harness)"
)
# Without streaming, a long answer takes a while to arrive in full.
TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class OpenAIChatClient:
    """A `ModelClient` over HTTP, in the OpenAI Chat Completions format.

    Use it as an async context manager: it owns its `httpx.AsyncClient`.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        session_header: str | None = None,
        session_id: str | None = None,
    ) -> None:
        headers = {"User-Agent": USER_AGENT}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if session_header:
            # One stable id per run of `maha`, as OpenCode asks third parties.
            headers[session_header] = session_id or str(uuid.uuid4())
        self._http = httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=TIMEOUT
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def complete(self, request: ModelRequest) -> ModelResponse:
        response = await self._http.post("chat/completions", json=_to_openai(request))
        completion = _Completion.model_validate_json(response.content)
        return _to_domain(completion, request)


def _to_openai(request: ModelRequest) -> dict[str, Any]:
    """The request body: the system prompt, if any, goes first as a message."""
    messages: list[dict[str, str]] = []
    if request.system:
        # `system`, not `developer`: it is the role compatible servers know.
        messages.append({"role": "system", "content": request.system})
    messages.extend(
        {"role": message.role, "content": message.text} for message in request.messages
    )
    return {"model": request.model, "messages": messages}


# What the adapter reads from the response. Unknown fields are ignored.


class _ResponseMessage(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _ResponseMessage


class _Completion(BaseModel):
    model: str | None = None
    choices: list[_Choice]


def _to_domain(completion: _Completion, request: ModelRequest) -> ModelResponse:
    content = completion.choices[0].message.content
    blocks = [TextBlock(text=content)] if content else []
    return ModelResponse(
        message=Message(role="assistant", blocks=blocks),
        stop_reason="other",
        usage=Usage(),
        model=completion.model or request.model,
    )
