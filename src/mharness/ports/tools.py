"""Port to a tool the model can ask to run (DESIGN §6, spec hito 4, §1.5)."""

from typing import Protocol

from pydantic import BaseModel

from mharness.domain.tools import Permission


class Tool[P: BaseModel](Protocol):
    """A tool: what the model sees of it, and how to run it.

    The model sees `name`, `description` and the JSON Schema of `params`. The
    loop validates the arguments with `params` before calling `run`.
    """

    name: str
    description: str
    params: type[P]
    permission: Permission

    async def run(self, params: P) -> str:
        """Run with validated parameters. Raises `ToolError` on an expected
        failure."""
        ...

    def summary(self, result: str) -> str:
        """A few words about a result, for the terminal: "3 lines"."""
        ...
