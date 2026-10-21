"""A `ModelClient` that answers from a script (DESIGN §12)."""

import asyncio
from collections.abc import AsyncGenerator, Iterable

from mharness.application.collect import collect
from mharness.domain.errors import ModelError
from mharness.domain.events import MessageEnd, ModelEvent, TextDelta, ToolCallDelta
from mharness.domain.messages import Block, Message, TextBlock, ToolCallBlock
from mharness.domain.model import ModelRequest, ModelResponse, StopReason, Usage

FAKE_MODEL = "fake-model"
END = MessageEnd(stop_reason="end_turn", usage=Usage(), model=FAKE_MODEL)


class Gate:
    """A pause inside a scripted stream, until the test calls `release()`."""

    def __init__(self) -> None:
        self._open = asyncio.Event()

    def release(self) -> None:
        self._open.set()

    async def wait(self) -> None:
        await self._open.wait()


class _Hang:
    """Waits forever, until the stream is cancelled (for Ctrl+C tests)."""


HANG = _Hang()

type StreamItem = ModelEvent | ModelError | Gate | _Hang
# A step answers one call: a whole response, an error, or a stream.
type Step = ModelResponse | ModelError | list[StreamItem]


def reply(
    text: str,
    *,
    stop_reason: StopReason = "end_turn",
    usage: Usage | None = None,
) -> ModelResponse:
    """An assistant answer with a single text block."""
    return ModelResponse(
        message=Message(role="assistant", blocks=[TextBlock(text=text)]),
        stop_reason=stop_reason,
        usage=usage or Usage(),
        model=FAKE_MODEL,
    )


def tool_calls(
    *calls: ToolCallBlock, text: str = "", usage: Usage | None = None
) -> ModelResponse:
    """An assistant answer that asks for tool calls, after optional text."""
    blocks: list[Block] = [TextBlock(text=text)] if text else []
    return ModelResponse(
        message=Message(role="assistant", blocks=[*blocks, *calls]),
        stop_reason="tool_use",
        usage=usage or Usage(),
        model=FAKE_MODEL,
    )


class FakeModelClient:
    """Answers each call with the next step of the script.

    Both methods take steps from the same script: `stream()` plays a whole
    response as events (its text in two deltas), and `complete()` collects a
    stream into a response. Every request received is kept in `requests`.
    Calling it more times than scripted fails the test.
    """

    def __init__(self, script: Iterable[Step]) -> None:
        self._script = list(script)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        step = self._next(request)
        if isinstance(step, ModelError):
            raise step
        if isinstance(step, ModelResponse):
            return step
        return await collect(_play(step))

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelEvent]:
        step = self._next(request)
        if isinstance(step, ModelResponse):
            step = _as_events(step)
        elif isinstance(step, ModelError):
            step = [step]
        async for event in _play(step):
            yield event

    def _next(self, request: ModelRequest) -> Step:
        self.requests.append(request)
        if not self._script:
            raise AssertionError(
                f"FakeModelClient: script exhausted at call {len(self.requests)}"
            )
        return self._script.pop(0)


def _as_events(response: ModelResponse) -> list[StreamItem]:
    text = response.message.text
    half = (len(text) + 1) // 2
    deltas: list[StreamItem] = [
        TextDelta(text=piece) for piece in (text[:half], text[half:]) if piece
    ]
    calls = [b for b in response.message.blocks if isinstance(b, ToolCallBlock)]
    deltas.extend(
        ToolCallDelta(index=i, id=call.id, name=call.name, arguments=call.arguments)
        for i, call in enumerate(calls)
    )
    end = MessageEnd(
        stop_reason=response.stop_reason, usage=response.usage, model=response.model
    )
    return [*deltas, end]


async def _play(items: list[StreamItem]) -> AsyncGenerator[ModelEvent]:
    for item in items:
        if isinstance(item, Gate):
            await item.wait()
        elif isinstance(item, _Hang):
            await asyncio.Event().wait()
        elif isinstance(item, ModelError):
            raise item
        else:
            yield item
