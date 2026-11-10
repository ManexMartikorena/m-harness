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
    UsageSoFar,
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
        # Calls by index and, if a server reuses an index for another call
        # (a new id), by their order within it (deep audit after hito 9).
        self._calls: dict[tuple[int, int], _PartialCall] = {}
        self._latest: dict[int, int] = {}
        self._end: MessageEnd | None = None
        # What the call used before it ended, if the provider said.
        self.so_far: UsageSoFar | None = None

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
                call = self._call(event)
                # The id comes once, in the first piece.
                call.id = call.id or event.id
                # The name comes whole, once: a server that repeats it must
                # not make another (audit after hito 10, B3; as the AI SDK).
                call.name = call.name or event.name or ""
                call.arguments += event.arguments
            case MessageEnd():
                self._end = event
            case UsageSoFar():
                self.so_far = event

    def _call(self, event: ToolCallDelta) -> _PartialCall:
        """The call this piece belongs to: a new id with a name at an index
        already in use starts another call. Without a name it is the same
        call: some servers send another id in every piece (review of the
        deep audit)."""
        order = self._latest.get(event.index, 0)
        call = self._calls.get((event.index, order))
        renamed = event.id and call is not None and call.id and event.id != call.id
        if renamed and event.name:
            order += 1
            self._latest[event.index] = order
            call = None
        if call is None:
            call = self._calls[event.index, order] = _PartialCall()
        return call

    @property
    def text(self) -> str:
        """The text so far, also before the answer ends (spec hito 6,
        §1.7)."""
        # Each block's text, joined as Message.text does (deep audit after
        # hito 9): two paragraphs must not run together.
        return "\n".join(
            part.text for _, part in sorted(self._text_blocks.items()) if part.text
        )

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
        for (index, _order), call in sorted(self._calls.items()):
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
