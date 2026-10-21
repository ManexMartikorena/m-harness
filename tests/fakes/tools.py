"""A `Tool` for tests: answers from a script (spec hito 4, §3.1)."""

import asyncio

from pydantic import BaseModel, Field

from mharness.domain.approval import ApprovalRequest
from mharness.domain.tools import Permission


class EchoParams(BaseModel):
    text: str = Field(description="The text to echo")


class FakeTool:
    """Returns `echo: <text>`, or the scripted results and errors in order.

    Every call is kept in `calls`. With `gate`, each run waits until the test
    sets it.
    """

    params = EchoParams

    def __init__(
        self,
        name: str = "echo",
        *,
        results: list[str | Exception] | None = None,
        permission: Permission = "read",
        gate: asyncio.Event | None = None,
    ) -> None:
        self.name = name
        self.description = f"Echo a text ({name})."
        self.permission: Permission = permission
        self._results = list(results or [])
        self._gate = gate
        self.calls: list[EchoParams] = []

    def approval(self, params: EchoParams) -> ApprovalRequest | None:
        return None

    async def run(self, params: EchoParams) -> str:
        self.calls.append(params)
        if self._gate is not None:
            await self._gate.wait()
        if not self._results:
            return f"echo: {params.text}"
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def summary(self, result: str) -> str:
        return f"{len(result)} chars"
