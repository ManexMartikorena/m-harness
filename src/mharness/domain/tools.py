"""What a tool may do, and how it fails (spec hito 4, §1.5)."""

from typing import Literal

# `read` runs without asking; `effect` will need approval (hito 5).
type Permission = Literal["read", "effect"]


class ToolError(Exception):
    """An expected failure of a tool, explained to the model.

    For example: the file does not exist. The loop sends the message back as
    an error result, and the model can correct itself.
    """
