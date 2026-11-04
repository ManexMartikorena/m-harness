"""A `ProjectInfo` in memory (spec hito 10)."""

from collections.abc import Sequence
from datetime import date

from mharness.domain.prompt import Environment, Instructions, Layer

ENVIRONMENT = Environment(
    cwd="/home/ana/tienda",
    git_root="/home/ana/tienda",
    platform="linux",
    shell="/bin/sh",
    today=date(2026, 11, 4),
)


class MemoryProject:
    """Gives the environment and the instruction layers it is given, and
    counts how often it is read."""

    def __init__(
        self,
        layers: Sequence[Layer] = (),
        *,
        warnings: Sequence[str] = (),
        environment: Environment = ENVIRONMENT,
    ) -> None:
        self.layers = list(layers)
        self.warnings = tuple(warnings)
        self.env = environment
        self.reads = 0

    async def environment(self) -> Environment:
        return self.env

    async def instructions(self) -> Instructions:
        self.reads += 1
        return Instructions(layers=tuple(self.layers), warnings=self.warnings)
