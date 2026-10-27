"""The whole answer, built from the events of a stream (spec hito 3, §1.5).

Tool calls are joined by their `index` (spec hito 4, §1.3).
"""

from dataclasses import dataclass

from mharness.domain.errors import ModelResponseError
from mharness.domain.events import MessageEnd, ModelEvent, TextDelta, ToolCallDelta
from mharness.domain.messages import Block, Message, TextBlock, ToolCallBlock
from mharness.domain.model import ModelResponse


@dataclass
class _PartialCall:
    id: str | None = None
    name: str = ""
    arguments: str = ""


class Accumulator:
    """Collects events one by one; `response()` gives the answer so far."""

    def __init__(self) -> None:
        self._texts: list[str] = []
        self._calls: dict[int, _PartialCall] = {}
        self._end: MessageEnd | None = None

    def add(self, event: ModelEvent) -> None:
        match event:
            case TextDelta(text=text):
                self._texts.append(text)
            case ToolCallDelta():
                call = self._calls.setdefault(event.index, _PartialCall())
                # The id comes once, in the first piece.
                call.id = call.id or event.id
                call.name += event.name or ""
                call.arguments += event.arguments
            case MessageEnd():
                self._end = event

    @property
    def text(self) -> str:
        """The text so far, also before the answer ends (spec hito 6,
        §1.7)."""
        return "".join(self._texts)

    def response(self) -> ModelResponse:
        """The answer. Raises `ModelResponseError` if it never ended."""
        if self._end is None:
            raise ModelResponseError("stream ended before the answer was complete")
        text = self.text
        blocks: list[Block] = [TextBlock(text=text)] if text else []
        for index in sorted(self._calls):
            call = self._calls[index]
            if not call.id or not call.name:
                raise ModelResponseError("a tool call came without its id or name")
            blocks.append(
                ToolCallBlock(id=call.id, name=call.name, arguments=call.arguments)
            )
        return ModelResponse(
            message=Message(role="assistant", blocks=blocks),
            stop_reason=self._end.stop_reason,
            usage=self._end.usage,
            model=self._end.model,
            cost=self._end.cost,
        )
