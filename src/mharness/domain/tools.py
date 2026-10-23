"""What a tool may do, and how it fails (spec hito 4, §1.5)."""

from typing import Literal

# `read` runs without asking, unless its path asks (outside the working
# directory, a secret); `effect` always asks (spec hito 5, §1.2).
type Permission = Literal["read", "effect"]


class ToolError(Exception):
    """An expected failure of a tool, explained to the model.

    For example: the file does not exist. The loop sends the message back as
    an error result, and the model can correct itself.
    """
