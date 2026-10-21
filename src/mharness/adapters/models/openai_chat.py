"""Adapter for the OpenAI Chat Completions format (spec hito 2, §1.8).

`stream()` reads the answer as Server-Sent Events (spec hito 3, §1.11).

Translates between the domain types and the JSON of any server that speaks
this format: OpenCode Go, OpenCode Zen, OpenRouter, Ollama… It decides nothing
about the agent.
"""

import codecs
import uuid
from collections.abc import AsyncIterator
from importlib.metadata import version
from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import BaseModel, Field, ValidationError

from mharness.adapters.models.sse import parse_sse
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
from mharness.domain.model import ModelRequest, ModelResponse, StopReason, Usage

USER_AGENT = (
    f"maha/{version('m-harness')} (+https://github.com/ManexMartikorena/m-harness)"
)
# `read` is the longest silence between two chunks, not the time of the whole
# answer: a long answer that keeps arriving is never cut (spec hito 3, §1.8).
TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

STOP_REASONS: dict[str, StopReason] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "content_filter",
}
# The provider's error message is shown to the user, cut to this length.
MAX_PROVIDER_MESSAGE = 300


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
        self._api_key = api_key
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
        """Send the request; raise a `ModelError` if anything goes wrong."""
        try:
            response = await self._http.post(
                "chat/completions", json=_to_openai(request)
            )
        except httpx.TimeoutException as exc:
            raise ModelUnavailableError("the provider took too long to answer") from exc
        except httpx.TransportError as exc:
            reason = str(exc) or type(exc).__name__
            raise ModelUnavailableError(f"cannot reach the provider: {reason}") from exc
        if not response.is_success:
            raise self._status_error(response)
        try:
            completion = _Completion.model_validate_json(response.content)
        except ValidationError:
            # The body is untrusted: it is not copied into the error.
            raise ModelResponseError(
                "the provider's response could not be understood"
            ) from None
        return _to_domain(completion, request)

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        """Yield the answer as it arrives; raise a `ModelError` on failure."""
        body = {
            **_to_openai(request),
            "stream": True,
            # OpenAI only sends usage if asked; OpenCode sends it anyway.
            "stream_options": {"include_usage": True},
        }
        async with self._http.stream("POST", "chat/completions", json=body) as response:
            async for event in _events(response, request):
                yield event

    def _status_error(self, response: httpx.Response) -> ModelError:
        status = response.status_code
        detail = _provider_message(response)
        if detail and self._api_key:
            # Never show the key, even if the provider echoes it back.
            detail = detail.replace(self._api_key, "[redacted]")
        if detail:
            detail = detail[:MAX_PROVIDER_MESSAGE]
        message = f"HTTP {status}: {detail}" if detail else f"HTTP {status}"
        if status in (401, 403):
            return ModelAuthError(message)
        if status == 429:
            return ModelRateLimitError(message)
        if status >= 500:
            return ModelUnavailableError(message)
        return ModelRequestError(message)


def _provider_message(response: httpx.Response) -> str | None:
    """The `error.message` of an OpenAI error body, if there is one."""
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    if not isinstance(message, str) or not message.strip():
        return None
    return message.strip()


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


# What the adapter reads from the response. Unknown fields (such as
# `reasoning_content`) are ignored; missing or null counters count as 0.


class _ResponseMessage(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _ResponseMessage
    finish_reason: str | None = None


class _PromptTokensDetails(BaseModel):
    cached_tokens: int | None = None


class _Usage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_tokens_details: _PromptTokensDetails | None = None


class _Completion(BaseModel):
    model: str | None = None
    choices: list[_Choice] = Field(min_length=1)
    usage: _Usage | None = None


def _to_domain(completion: _Completion, request: ModelRequest) -> ModelResponse:
    choice = completion.choices[0]
    content = choice.message.content
    blocks = [TextBlock(text=content)] if content else []
    return ModelResponse(
        message=Message(role="assistant", blocks=blocks),
        stop_reason=STOP_REASONS.get(choice.finish_reason or "", "other"),
        usage=_usage(completion.usage),
        model=completion.model or request.model,
    )


# What the adapter reads from each chunk of a stream. The usage chunk comes
# last, with `choices` empty.


class _Delta(BaseModel):
    content: str | None = None


class _ChunkChoice(BaseModel):
    delta: _Delta = Field(default_factory=_Delta)
    finish_reason: str | None = None


class _Chunk(BaseModel):
    model: str | None = None
    choices: list[_ChunkChoice] = []
    usage: _Usage | None = None


async def _events(
    response: httpx.Response, request: ModelRequest
) -> AsyncIterator[ModelEvent]:
    """Translate the chunks; `MessageEnd` goes last, when all is known."""
    finish_reason: str | None = None
    usage: _Usage | None = None
    model: str | None = None
    async for data in parse_sse(_text(response)):
        if data == "[DONE]":
            # Anything after it is not read; leaving closes the connection.
            break
        chunk = _Chunk.model_validate_json(data)
        model = chunk.model or model
        usage = chunk.usage or usage
        if not chunk.choices:
            continue
        # `maha` never asks for several choices (`n`).
        choice = chunk.choices[0]
        if choice.delta.content:
            yield TextDelta(text=choice.delta.content)
        finish_reason = choice.finish_reason or finish_reason
    yield MessageEnd(
        stop_reason=STOP_REASONS.get(finish_reason or "", "other"),
        usage=_usage(usage),
        model=model or request.model,
    )


async def _text(response: httpx.Response) -> AsyncIterator[str]:
    """The body as text. The incremental decoder never cuts a character split
    between two network chunks, and drops a leading BOM."""
    decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="replace")
    async for chunk in response.aiter_bytes():
        if text := decoder.decode(chunk):
            yield text
    if text := decoder.decode(b"", final=True):
        yield text


def _usage(usage: _Usage | None) -> Usage:
    if usage is None:
        return Usage()
    details = usage.prompt_tokens_details
    return Usage(
        input_tokens=usage.prompt_tokens or 0,
        output_tokens=usage.completion_tokens or 0,
        cache_read_tokens=(details.cached_tokens or 0) if details else 0,
    )
