"""The whole answer, built from the events of a stream (spec hito 3, §1.5)."""

from collections.abc import AsyncIterable

from mharness.domain.errors import ModelResponseError
from mharness.domain.events import MessageEnd, ModelEvent, TextDelta
from mharness.domain.messages import Block, Message, TextBlock
from mharness.domain.model import ModelResponse


class Accumulator:
    """Collects events one by one; `response()` gives the answer so far."""

    def __init__(self) -> None:
        self._texts: list[str] = []
        self._end: MessageEnd | None = None

    def add(self, event: ModelEvent) -> None:
        match event:
            case TextDelta(text=text):
                self._texts.append(text)
            case MessageEnd():
                self._end = event

    def response(self) -> ModelResponse:
        """The answer. Raises `ModelResponseError` if it never ended."""
        if self._end is None:
            raise ModelResponseError("stream ended before the answer was complete")
        text = "".join(self._texts)
        blocks: list[Block] = [TextBlock(text=text)] if text else []
        return ModelResponse(
            message=Message(role="assistant", blocks=blocks),
            stop_reason=self._end.stop_reason,
            usage=self._end.usage,
            model=self._end.model,
        )


async def collect(events: AsyncIterable[ModelEvent]) -> ModelResponse:
    """Consume a whole stream and return the answer."""
    accumulator = Accumulator()
    async for event in events:
        accumulator.add(event)
    return accumulator.response()
