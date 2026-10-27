"""Adapter for the OpenAI Chat Completions format (spec hito 2, §1.8).

`stream()` reads the answer as Server-Sent Events (spec hito 3, §1.11).

Translates between the domain types and the JSON of any server that speaks
this format: OpenCode Go, OpenCode Zen, OpenRouter, Ollama… It decides nothing
about the agent.
"""

import codecs
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import BaseModel, Field, ValidationError

from mharness import __version__
from mharness.adapters.models.sse import parse_sse
from mharness.domain.errors import (
    ModelAuthError,
    ModelError,
    ModelRateLimitError,
    ModelRequestError,
    ModelResponseError,
    ModelUnavailableError,
)
from mharness.domain.events import MessageEnd, ModelEvent, TextDelta, ToolCallDelta
from mharness.domain.messages import (
    Block,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from mharness.domain.model import ModelRequest, ModelResponse, StopReason, Usage

USER_AGENT = f"maha/{__version__} (+https://github.com/ManexMartikorena/m-harness)"
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
        except httpx.RequestError as exc:
            # Every request error, not only transport ones, and without the
            # key, as in stream() (spec mejora-2026-10-23-deuda-hito-5, A7).
            reason = self._safe(str(exc)) or type(exc).__name__
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

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelEvent]:
        """Yield the answer as it arrives; raise a `ModelError` on failure."""
        body = {
            **_to_openai(request),
            "stream": True,
            # OpenAI only sends usage if asked; OpenCode sends it anyway.
            "stream_options": {"include_usage": True},
        }
        try:
            async with self._http.stream(
                "POST", "chat/completions", json=body
            ) as response:
                if not response.is_success:
                    await response.aread()
                    raise self._status_error(response)
                await self._check_streaming(response)
                async for event in self._events(response, request):
                    yield event
        except httpx.TimeoutException as exc:
            raise ModelUnavailableError("the provider took too long to answer") from exc
        except httpx.RequestError as exc:
            # Also a failure after the finish reason: the stream did not end
            # cleanly, so the answer is not trusted (spec hito 3, §1.8).
            reason = self._safe(str(exc)) or type(exc).__name__
            raise ModelUnavailableError(
                f"the connection to the provider failed: {reason}"
            ) from exc

    async def _check_streaming(self, response: httpx.Response) -> None:
        """Fail if a 200 answer is not an event stream."""
        content_type = response.headers.get("content-type", "").lower()
        if content_type.startswith("text/event-stream"):
            return
        detail = None
        if content_type.startswith("application/json"):
            await response.aread()
            detail = self._safe(_provider_message(response))
        raise ModelResponseError(detail or "the provider did not stream")

    async def _events(
        self, response: httpx.Response, request: ModelRequest
    ) -> AsyncIterator[ModelEvent]:
        """Translate the chunks; `MessageEnd` goes last, when all is known."""
        finish_reason: str | None = None
        usage: _Usage | None = None
        model: str | None = None
        async for data in parse_sse(_text(response)):
            if data == "[DONE]":
                # Anything after it is not read; leaving closes the connection.
                break
            try:
                chunk = _Chunk.model_validate_json(data)
            except ValidationError:
                # The body is untrusted: it is not copied into the error.
                raise ModelResponseError(
                    "a chunk of the stream could not be understood"
                ) from None
            if chunk.error is not None:
                detail = self._safe(_error_message(chunk.error))
                message = "the provider failed while answering"
                raise ModelUnavailableError(
                    f"{message}: {detail}" if detail else message
                )
            model = chunk.model or model
            usage = chunk.usage or usage
            if not chunk.choices:
                continue
            # `maha` never asks for several choices (`n`).
            choice = chunk.choices[0]
            if choice.delta.content:
                yield TextDelta(text=choice.delta.content)
            # A refusal is text the person must see (spec hito 5, §1.11).
            if choice.delta.refusal:
                yield TextDelta(text=choice.delta.refusal)
            # `tool_calls` may come as an explicit null (spec hito 4, §1.1).
            for call in choice.delta.tool_calls or []:
                function = call.function or _DeltaFunction()
                yield ToolCallDelta(
                    index=call.index,
                    id=call.id,
                    name=function.name,
                    arguments=function.arguments or "",
                )
            finish_reason = choice.finish_reason or finish_reason
        if finish_reason is None:
            raise ModelResponseError("stream ended before the answer was complete")
        yield MessageEnd(
            stop_reason=STOP_REASONS.get(finish_reason, "other"),
            usage=_usage(usage),
            model=model or request.model,
        )

    def _safe(self, detail: str | None) -> str | None:
        """A provider's text, ready to show: without the key, and cut."""
        if not detail:
            return None
        if self._api_key:
            # Never show the key, even if the provider echoes it back. Before
            # cutting, or a cut key would slip through.
            detail = detail.replace(self._api_key, "[redacted]")
        return detail[:MAX_PROVIDER_MESSAGE]

    def _status_error(self, response: httpx.Response) -> ModelError:
        status = response.status_code
        detail = self._safe(_provider_message(response))
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
    return _error_message(body.get("error") if isinstance(body, dict) else None)


def _error_message(error: Any) -> str | None:
    """The message of an `error` value: an object with `message`, or text."""
    message = error.get("message") if isinstance(error, dict) else error
    if not isinstance(message, str) or not message.strip():
        return None
    return message.strip()


def _to_openai(request: ModelRequest) -> dict[str, Any]:
    """The request body: the system prompt, if any, goes first as a message."""
    messages: list[dict[str, Any]] = []
    if request.system:
        # `system`, not `developer`: it is the role compatible servers know.
        messages.append({"role": "system", "content": request.system})
    for message in request.messages:
        messages.extend(_message_to_openai(message))
    body: dict[str, Any] = {"model": request.model, "messages": messages}
    if request.tools:
        # No `tool_choice` (the default, "auto", is what is wanted) and no
        # `parallel_tool_calls` (OpenCode ignores it) (spec hito 4, §1.4).
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in request.tools
        ]
    return body


# Added to an answer cut by Ctrl+C.
INTERRUPTED_MARK = "\n\n[interrupted by the user]"


def _message_to_openai(message: Message) -> list[dict[str, Any]]:
    """One domain message as OpenAI messages: a `tool` message becomes one
    message per result."""
    if message.role == "tool":
        # OpenAI has no `is_error`: an error result already says "error:".
        return [
            {"role": "tool", "tool_call_id": block.call_id, "content": block.content}
            for block in message.blocks
            if isinstance(block, ToolResultBlock)
        ]
    calls = [block for block in message.blocks if isinstance(block, ToolCallBlock)]
    text = message.text
    if message.interrupted:
        # So the model knows it did not finish (spec hito 6, §1.7).
        text += INTERRUPTED_MARK
    if not calls:
        return [{"role": message.role, "content": text}]
    return [
        {
            "role": message.role,
            # Required unless there are tool calls: null when there is no text.
            "content": text or None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in calls
            ],
        }
    ]


# What the adapter reads from the response. Unknown fields (such as
# `reasoning_content`) are ignored; missing or null counters count as 0.


class _Function(BaseModel):
    name: str
    arguments: str


class _ToolCall(BaseModel):
    id: str
    function: _Function


class _ResponseMessage(BaseModel):
    content: str | None = None
    refusal: str | None = None
    tool_calls: list[_ToolCall] | None = None


class _Choice(BaseModel):
    message: _ResponseMessage
    finish_reason: str | None = None


class _PromptTokensDetails(BaseModel):
    cached_tokens: int | None = None


class _CompletionTokensDetails(BaseModel):
    reasoning_tokens: int | None = None


class _Usage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_tokens_details: _PromptTokensDetails | None = None
    completion_tokens_details: _CompletionTokensDetails | None = None


class _Completion(BaseModel):
    model: str | None = None
    choices: list[_Choice] = Field(min_length=1)
    usage: _Usage | None = None


def _to_domain(completion: _Completion, request: ModelRequest) -> ModelResponse:
    choice = completion.choices[0]
    # A refusal is text the person must see (spec hito 5, §1.11).
    texts = (choice.message.content, choice.message.refusal)
    blocks: list[Block] = [TextBlock(text=text) for text in texts if text]
    blocks.extend(
        ToolCallBlock(
            id=call.id, name=call.function.name, arguments=call.function.arguments
        )
        for call in choice.message.tool_calls or []
    )
    return ModelResponse(
        message=Message(role="assistant", blocks=blocks),
        stop_reason=STOP_REASONS.get(choice.finish_reason or "", "other"),
        usage=_usage(completion.usage),
        model=completion.model or request.model,
    )


# What the adapter reads from each chunk of a stream. The usage chunk comes
# last, with `choices` empty.


class _DeltaFunction(BaseModel):
    name: str | None = None
    arguments: str | None = None


class _DeltaToolCall(BaseModel):
    index: int
    id: str | None = None
    function: _DeltaFunction | None = None


class _Delta(BaseModel):
    content: str | None = None
    refusal: str | None = None
    tool_calls: list[_DeltaToolCall] | None = None


class _ChunkChoice(BaseModel):
    delta: _Delta = Field(default_factory=_Delta)
    finish_reason: str | None = None


class _Chunk(BaseModel):
    model: str | None = None
    choices: list[_ChunkChoice] = []
    usage: _Usage | None = None
    # Format not documented by OpenCode (spec hito 3, §10): read defensively.
    error: Any = None


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
    prompt = usage.prompt_tokens_details
    completion = usage.completion_tokens_details
    return Usage(
        input_tokens=_count(usage.prompt_tokens),
        output_tokens=_count(usage.completion_tokens),
        cache_read_tokens=_count(prompt.cached_tokens if prompt else None),
        reasoning_tokens=_count(completion.reasoning_tokens if completion else None),
    )


def _count(tokens: int | None) -> int:
    """A count the provider sent; missing, null or negative is 0."""
    return max(tokens or 0, 0)
