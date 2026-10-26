"""Messages of a conversation, made of content blocks (DESIGN §5)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

type Role = Literal["user", "assistant", "tool"]


class TextBlock(BaseModel, frozen=True):
    """A piece of plain text inside a message."""

    # Discriminator: tells block types apart when more of them exist.
    type: Literal["text"] = "text"
    text: str


class ToolCallBlock(BaseModel, frozen=True):
    """The model asks to run a tool (spec hito 4, §1.2)."""

    type: Literal["tool_call"] = "tool_call"
    # Pairs the call with its result.
    id: str
    name: str
    # JSON text, exactly as the model wrote it: it may be invalid, and the
    # attempt must stay in the history next to its error.
    arguments: str


class ToolResultBlock(BaseModel, frozen=True):
    """What a tool call returned, sent back to the model."""

    type: Literal["tool_result"] = "tool_result"
    call_id: str
    content: str
    is_error: bool = False


# Validated by `type`, so a message read from JSON gets the right blocks.
type Block = Annotated[
    TextBlock | ToolCallBlock | ToolResultBlock, Field(discriminator="type")
]


class Message(BaseModel, frozen=True):
    """One turn of the conversation: who speaks and what they say.

    The assistant writes text and tool calls; a `tool` message carries one
    result per call.
    """

    role: Role
    blocks: list[Block]
    # Cut by Ctrl+C while the model wrote it: a fact of the conversation,
    # that each adapter tells its model in its own way (spec hito 6, §1.7).
    interrupted: bool = False

    @property
    def text(self) -> str:
        """The text blocks, joined with a newline."""
        return "\n".join(
            block.text for block in self.blocks if isinstance(block, TextBlock)
        )
