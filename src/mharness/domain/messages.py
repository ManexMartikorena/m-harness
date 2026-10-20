"""Messages of a conversation, made of content blocks (DESIGN §5)."""

from typing import Literal

from pydantic import BaseModel

type Role = Literal["user", "assistant", "tool"]


class TextBlock(BaseModel, frozen=True):
    """A piece of plain text inside a message."""

    # Discriminator: tells block types apart when more of them exist.
    type: Literal["text"] = "text"
    text: str


class Message(BaseModel, frozen=True):
    """One turn of the conversation: who speaks and what they say."""

    role: Role
    blocks: list[TextBlock]

    @property
    def text(self) -> str:
        """The text blocks, joined with a newline."""
        return "\n".join(block.text for block in self.blocks)
