"""Adapter for Anthropic's Messages API (spec hito 9).

Translates between the domain types and the JSON of any server that speaks
this format: Anthropic's API, OpenCode Go and Zen (Claude, MiniMax, Qwen)…
It decides nothing about the agent. Facts checked against Anthropic's docs
and OpenCode on 2026-11-03 (spec, §1.0).
"""

import asyncio
import hashlib
import json
import re
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from decimal import Decimal
from types import TracebackType
from typing import Any, Literal, Self

import httpx

from mharness.adapters.models.http import (
    STALL_SECONDS,
    TIMEOUT,
    USER_AGENT,
    check_streaming,
    count,
    error_message,
    provider_cost,
    safe,
    status_error,
    text,
)
from mharness.adapters.models.sse import parse_sse
from mharness.domain.errors import (
    ModelRateLimitError,
    ModelResponseError,
    ModelUnavailableError,
)
from mharness.domain.events import (
    MessageEnd,
    ModelEvent,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
)
from mharness.domain.messages import (
    Block,
    Message,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from mharness.domain.model import ModelRequest, ModelResponse, StopReason, Usage

# The latest version, the one Anthropic recommends; a provider may ask for
# another (spec hito 9, decision 2).
VERSION = "2026-10-21"
# The answer's ceiling when the catalog does not know the model's (spec
# hito 9, §1.6): paid only for what is written.
DEFAULT_MAX_TOKENS = 32_000

type CacheTtl = Literal["5m", "1h"]

STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "model_context_window_exceeded": "max_tokens",
    "refusal": "content_filter",
}
# Added to an answer cut by Ctrl+C (spec hito 6, §1.7), as in OpenAI.
INTERRUPTED_MARK = "[interrupted by the user]"


class AnthropicClient:
    """A `ModelClient` over HTTP, in Anthropic's Messages API format.

    Use it as an async context manager: it owns its `httpx.AsyncClient`.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        session_header: str | None = None,
        session_id: str | None = None,
        version: str = VERSION,
        cache_ttl: CacheTtl = "5m",
    ) -> None:
        self._api_key = api_key
        self._cache_ttl = cache_ttl
        headers = {"User-Agent": USER_AGENT, "anthropic-version": version}
        if api_key:
            # The current form; the old `x-api-key` still works (spec, §1.0).
            headers["Authorization"] = f"Bearer {api_key}"
        if session_header:
            # One stable id per run of `maha`: OpenCode needs it here too.
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
                "messages", json=_to_anthropic(request, self._cache_ttl)
            )
        except httpx.TimeoutException as exc:
            raise ModelUnavailableError("the provider took too long to answer") from exc
        except httpx.RequestError as exc:
            reason = self._safe(str(exc)) or type(exc).__name__
            raise ModelUnavailableError(f"cannot reach the provider: {reason}") from exc
        if not response.is_success:
            raise status_error(response, self._api_key)
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("content"), list):
            # The body is untrusted: it is not copied into the error.
            raise ModelResponseError("the provider's response could not be understood")
        return _to_domain(body, request)

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelEvent]:
        """Yield the answer as it arrives; raise a `ModelError` on failure."""
        body = {**_to_anthropic(request, self._cache_ttl), "stream": True}
        try:
            async with self._http.stream("POST", "messages", json=body) as response:
                if not response.is_success:
                    await response.aread()
                    raise status_error(response, self._api_key)
                await check_streaming(response, self._api_key)
                async for event in self._events(response, request):
                    yield event
        except httpx.TimeoutException as exc:
            raise ModelUnavailableError("the provider took too long to answer") from exc
        except httpx.RequestError as exc:
            # Also a failure after the stop reason: the stream did not end
            # cleanly, so the answer is not trusted (spec hito 3, §1.8).
            reason = self._safe(str(exc)) or type(exc).__name__
            raise ModelUnavailableError(
                f"the connection to the provider failed: {reason}"
            ) from exc

    async def _events(
        self, response: httpx.Response, request: ModelRequest
    ) -> AsyncIterator[ModelEvent]:
        """Translate the events (spec hito 9, §1.4); `MessageEnd` goes last,
        when all is known."""
        state = _Stream(request.model)
        datas = parse_sse(text(response))
        loop = asyncio.get_running_loop()
        # Pings keep the connection alive but are no progress.
        progress = loop.time()
        while not state.stopped:
            try:
                remaining = max(progress + STALL_SECONDS - loop.time(), 0.0)
                async with asyncio.timeout(remaining):
                    data = await anext(datas)
            except StopAsyncIteration:
                break
            except TimeoutError:
                raise ModelUnavailableError(
                    f"the provider sent nothing for {STALL_SECONDS:g} s"
                ) from None
            event = _object(data)
            kind = event.get("type")
            if kind == "ping":
                continue
            progress = loop.time()
            if kind == "error":
                raise self._stream_error(event.get("error"))
            for translated in state.read(event):
                yield translated
        for translated in state.finish():
            yield translated

    def _stream_error(self, error: Any) -> Exception:
        detail = self._safe(error_message(error))
        message = "the provider failed while answering"
        message = f"{message}: {detail}" if detail else message
        if isinstance(error, dict) and error.get("type") == "rate_limit_error":
            return ModelRateLimitError(message)
        return ModelUnavailableError(message)

    def _safe(self, detail: str | None) -> str | None:
        return safe(detail, self._api_key)


class _Stream:
    """What a stream told so far, and its events as the domain's."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.usage: dict[str, Any] = {}
        self.stop_reason: str | None = None
        self.stop_details: Any = None
        self.stopped = False
        # The tool calls by index, and whether their arguments came.
        self._calls: dict[int, bool] = {}
        self._text = False
        self._last = -1

    def read(self, event: dict[str, Any]) -> list[ModelEvent]:
        match event.get("type"):
            case "message_start":
                message = _dict(event.get("message"))
                self.model = _str(message.get("model")) or self.model
                self._count(message.get("usage"))
            case "content_block_start":
                return self._start(_index(event), _dict(event.get("content_block")))
            case "content_block_delta":
                return self._delta(_index(event), _dict(event.get("delta")))
            case "content_block_stop":
                index = _index(event)
                if self._calls.get(index) is False:
                    # A call without arguments takes none (spec, §1.4).
                    return [ToolCallDelta(index=index, arguments="{}")]
            case "message_delta":
                delta = _dict(event.get("delta"))
                self.stop_reason = _str(delta.get("stop_reason")) or self.stop_reason
                self.stop_details = delta.get("stop_details") or self.stop_details
                # Cumulative: the last one says it all.
                self._count(event.get("usage"))
            case "message_stop":
                self.stopped = True
        # Unknown events are ignored, as the versioning policy asks.
        return []

    def _count(self, usage: Any) -> None:
        """Take the counts that came; a null is no count, not zero (deep
        audit after hito 9): it must not wipe what came before."""
        self.usage |= {
            key: value for key, value in _dict(usage).items() if value is not None
        }

    def _start(self, index: int, block: dict[str, Any]) -> list[ModelEvent]:
        self._last = max(self._last, index)
        match block.get("type"):
            case "text":
                return self._said(index, _str(block.get("text")))
            case "tool_use":
                self._calls[index] = False
                return [
                    ToolCallDelta(
                        index=index,
                        id=_str(block.get("id")),
                        name=_str(block.get("name")),
                    )
                ]
            case "thinking":
                # The block exists even if no delta comes.
                return [
                    ReasoningDelta(
                        index=index,
                        text=_str(block.get("thinking")) or "",
                        signature=_str(block.get("signature")),
                    )
                ]
            case "redacted_thinking":
                return [ReasoningDelta(index=index, redacted=_str(block.get("data")))]
        return []

    def _delta(self, index: int, delta: dict[str, Any]) -> list[ModelEvent]:
        match delta.get("type"):
            case "text_delta":
                return self._said(index, _str(delta.get("text")))
            case "input_json_delta":
                piece = _str(delta.get("partial_json"))
                if not piece:
                    return []
                self._calls[index] = True
                return [ToolCallDelta(index=index, arguments=piece)]
            case "thinking_delta":
                thought = _str(delta.get("thinking"))
                return [ReasoningDelta(index=index, text=thought)] if thought else []
            case "signature_delta":
                signature = _str(delta.get("signature"))
                return [ReasoningDelta(index=index, signature=signature)]
        return []

    def _said(self, index: int, said: str | None) -> list[ModelEvent]:
        if not said:
            return []
        self._text = True
        return [TextDelta(text=said, block=index)]

    def finish(self) -> list[ModelEvent]:
        if not self.stopped or self.stop_reason is None:
            # The server or the network cut it: the provider's, as any other
            # cut (deep audit after hito 9, I15, a decision of the maintainer).
            raise ModelUnavailableError("stream ended before the answer was complete")
        events: list[ModelEvent] = []
        explanation = _refusal(self.stop_reason, self.stop_details, self._text)
        if explanation:
            events.append(TextDelta(text=explanation, block=self._last + 1))
        events.append(
            MessageEnd(
                stop_reason=STOP_REASONS.get(self.stop_reason, "other"),
                usage=_usage(self.usage),
                model=self.model,
                cost=_cost(self.usage),
            )
        )
        return events


def _to_anthropic(request: ModelRequest, cache_ttl: CacheTtl) -> dict[str, Any]:
    """The request body (spec hito 9, §1.3)."""
    body: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
    }
    if request.system:
        body["system"] = request.system
    if request.tools:
        body["tools"] = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in request.tools
        ]
    body["messages"] = _messages(request.messages)
    # Automatic caching: the breakpoint moves with the conversation (§1.8).
    cache: dict[str, str] = {"type": "ephemeral"}
    if cache_ttl != "5m":
        cache["ttl"] = cache_ttl
    body["cache_control"] = cache
    if request.effort is not None:
        body["output_config"] = {"effort": request.effort}
    return body


def _messages(messages: list[Message]) -> list[dict[str, Any]]:
    """The domain's messages as Anthropic's: `tool` ones become `user`
    ones, and two in a row of the same role become one."""
    out: list[dict[str, Any]] = []
    for message in messages:
        role = "user" if message.role == "tool" else message.role
        content = _content(message)
        if not content:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(content)
        else:
            out.append({"role": role, "content": content})
    return out


def _content(message: Message) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for block in message.blocks:
        match block:
            case TextBlock(text=said) if said.strip():
                content.append({"type": "text", "text": said})
            case ReasoningBlock(redacted=str() as data):
                content.append({"type": "redacted_thinking", "data": data})
            case ReasoningBlock(signature=str() as signature):
                # Unchanged, in its place (spec hito 9, §1.5).
                content.append(
                    {"type": "thinking", "thinking": block.text, "signature": signature}
                )
            case ToolCallBlock():
                content.append(
                    {
                        "type": "tool_use",
                        "id": _tool_id(block.id),
                        "name": block.name,
                        "input": _input(block.arguments),
                    }
                )
            case ToolResultBlock():
                result: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": _tool_id(block.call_id),
                    "content": block.content,
                }
                if block.is_error:
                    result["is_error"] = True
                content.append(result)
    if message.interrupted:
        content.append({"type": "text", "text": INTERRUPTED_MARK})
    return content


# What Anthropic accepts as a tool_use id.
_TOOL_ID = re.compile(r"[a-zA-Z0-9_-]+")


def _tool_id(call_id: str) -> str:
    """An id Anthropic accepts: as it is, or, if another server made it
    with other characters (`functions.read_file:0`), remade from it the
    same way for the call and its result (deep audit after hito 9, M2)."""
    if _TOOL_ID.fullmatch(call_id):
        return call_id
    digest = hashlib.sha256(call_id.encode("utf-8", "surrogatepass")).hexdigest()
    readable = re.sub(r"[^a-zA-Z0-9_-]", "_", call_id)[:40]
    return f"{readable}_{digest[:12]}"


def _input(arguments: str) -> dict[str, Any]:
    """The arguments as the object `input` asks for; `{}` if the model did
    not write one: its error is in the result that follows."""
    try:
        value = json.loads(arguments)
    except ValueError, RecursionError:
        return {}
    return value if isinstance(value, dict) else {}


def _to_domain(body: dict[str, Any], request: ModelRequest) -> ModelResponse:
    """A whole answer (spec hito 9, §1.10): the same rules as the stream."""
    blocks: list[Block] = []
    for raw in body["content"]:
        block = _dict(raw)
        match block.get("type"):
            case "text":
                if said := _str(block.get("text")):
                    blocks.append(TextBlock(text=said))
            case "thinking":
                blocks.append(
                    ReasoningBlock(
                        text=_str(block.get("thinking")) or "",
                        signature=_str(block.get("signature")) or None,
                    )
                )
            case "redacted_thinking":
                blocks.append(ReasoningBlock(redacted=_str(block.get("data"))))
            case "tool_use":
                call_id, name = _str(block.get("id")), _str(block.get("name"))
                if not call_id or not name:
                    raise ModelResponseError("a tool call came without its id or name")
                arguments = json.dumps(block.get("input") or {}, ensure_ascii=False)
                blocks.append(ToolCallBlock(id=call_id, name=name, arguments=arguments))
    stop_reason = _str(body.get("stop_reason")) or ""
    has_text = any(isinstance(block, TextBlock) for block in blocks)
    if explanation := _refusal(stop_reason, body.get("stop_details"), has_text):
        blocks.append(TextBlock(text=explanation))
    usage = _dict(body.get("usage"))
    return ModelResponse(
        message=Message(role="assistant", blocks=blocks),
        stop_reason=STOP_REASONS.get(stop_reason, "other"),
        usage=_usage(usage),
        model=_str(body.get("model")) or request.model,
        cost=_cost(usage),
    )


def _refusal(stop_reason: str, details: Any, has_text: bool) -> str | None:
    """Why the model declined, if it said nothing else: the person must
    see it (spec hito 5, §1.11)."""
    if stop_reason != "refusal" or has_text:
        return None
    return _str(_dict(details).get("explanation")) or None


def _usage(usage: dict[str, Any]) -> Usage:
    """The domain counts the whole prompt, as OpenAI: Anthropic's
    `input_tokens` is only what goes after the last cache point (§1.4)."""
    read = count(_int(usage.get("cache_read_input_tokens")))
    written = count(_int(usage.get("cache_creation_input_tokens")))
    details = _dict(usage.get("output_tokens_details"))
    hour = _dict(usage.get("cache_creation")).get("ephemeral_1h_input_tokens")
    return Usage(
        input_tokens=count(_int(usage.get("input_tokens"))) + read + written,
        output_tokens=count(_int(usage.get("output_tokens"))),
        cache_read_tokens=read,
        cache_write_tokens=written,
        cache_write_1h_tokens=min(count(_int(hour)), written),
        reasoning_tokens=count(_int(details.get("thinking_tokens"))),
    )


def _cost(usage: dict[str, Any]) -> Decimal | None:
    return provider_cost(usage.get("opencode"), usage.get("cost"))


def _object(data: str) -> dict[str, Any]:
    try:
        event = json.loads(data)
    except ValueError:
        event = None
    if not isinstance(event, dict):
        # The body is untrusted: it is not copied into the error.
        raise ModelResponseError("an event of the stream could not be understood")
    return event


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _index(event: dict[str, Any]) -> int:
    index = _int(event.get("index"))
    if index is None:
        raise ModelResponseError("an event of the stream came without its index")
    return index
