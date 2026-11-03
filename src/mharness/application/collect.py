"""The whole answer, built from the events of a stream (spec hito 3, §1.5).

Tool calls are joined by their `index` (spec hito 4, §1.3). Blocks come out
in the order of their index (spec hito 9, §1.5): OpenAI's text, which has
none, first, and its calls by index, as before; Anthropic's blocks exactly
as the model wrote them, which its reasoning needs to stay valid.
"""

from dataclasses import dataclass

from mharness.domain.errors import ModelResponseError
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
)
from mharness.domain.model import ModelResponse

# The index of a text without one (OpenAI): before every block.
_UNINDEXED = -1


@dataclass
class _PartialText:
    text: str = ""


@dataclass
class _PartialReasoning:
    text: str = ""
    signature: str | None = None
    redacted: str | None = None


@dataclass
class _PartialCall:
    id: str | None = None
    name: str = ""
    arguments: str = ""


class Accumulator:
    """Collects events one by one; `response()` gives the answer so far."""

    def __init__(self) -> None:
        self._texts: list[str] = []
        # Each kind of block by its index: a text and a call of OpenAI may
        # share an index, an Anthropic block never does.
        self._text_blocks: dict[int, _PartialText] = {}
        self._reasonings: dict[int, _PartialReasoning] = {}
        self._calls: dict[int, _PartialCall] = {}
        self._end: MessageEnd | None = None

    def add(self, event: ModelEvent) -> None:
        match event:
            case TextDelta(text=text, block=block):
                self._texts.append(text)
                index = _UNINDEXED if block is None else block
                self._text_blocks.setdefault(index, _PartialText()).text += text
            case ReasoningDelta():
                part = self._reasonings.setdefault(event.index, _PartialReasoning())
                part.text += event.text
                # Each comes once, whole.
                part.signature = event.signature or part.signature
                part.redacted = event.redacted or part.redacted
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
        indexed: list[tuple[int, Block]] = [
            (index, TextBlock(text=part.text))
            for index, part in self._text_blocks.items()
            if part.text
        ]
        indexed += [
            (
                index,
                ReasoningBlock(
                    text=part.text, signature=part.signature, redacted=part.redacted
                ),
            )
            for index, part in self._reasonings.items()
        ]
        for index, call in self._calls.items():
            if not call.id or not call.name:
                raise ModelResponseError("a tool call came without its id or name")
            indexed.append(
                (
                    index,
                    ToolCallBlock(id=call.id, name=call.name, arguments=call.arguments),
                )
            )
        # Stable: on a shared index (OpenAI), the text goes before the call.
        blocks = [block for _, block in sorted(indexed, key=lambda item: item[0])]
        return ModelResponse(
            message=Message(role="assistant", blocks=blocks),
            stop_reason=self._end.stop_reason,
            usage=self._end.usage,
            model=self._end.model,
            cost=self._end.cost,
        )
