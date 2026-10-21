"""The tools the model may use in a session (spec hito 4, §1.5).

What is not registered does not exist for the model (DESIGN §10). Effect tools
are accepted: the loop asks before running them (spec hito 5, §1.4).
"""

from collections.abc import Iterable
from typing import Any

from mharness.domain.model import ToolSpec
from mharness.ports.tools import Tool


class ToolRegistry:
    """Tools by name. Fixed once built: a tool result never changes it."""

    def __init__(self, tools: Iterable[Tool[Any]] = ()) -> None:
        self._tools: dict[str, Tool[Any]] = {}
        for tool in tools:
            self._add(tool)

    def _add(self, tool: Tool[Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f'tool "{tool.name}" is registered twice')
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any] | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[ToolSpec]:
        """The tools as the model sees them. The schema comes from the same
        Pydantic model that validates the arguments."""
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description,
                input_schema=tool.params.model_json_schema(),
            )
            for tool in self._tools.values()
        ]
