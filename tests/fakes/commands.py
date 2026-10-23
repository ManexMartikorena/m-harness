"""A `CommandRunner` for tests: answers from a script (spec hito 5, §3.1)."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from mharness.domain.commands import CommandResult


@dataclass(frozen=True)
class Ran:
    command: str
    cwd: Path
    time_limit: float
    env: dict[str, str]


class FakeRunner:
    """Answers each command with the next result of the script.

    Every command received is kept in `ran`. Running more than scripted
    fails the test.
    """

    def __init__(self, results: Iterable[CommandResult] = ()) -> None:
        self._results = list(results)
        self.ran: list[Ran] = []

    async def run(
        self, command: str, *, cwd: Path, time_limit: float, env: Mapping[str, str]
    ) -> CommandResult:
        self.ran.append(Ran(command, cwd, time_limit, dict(env)))
        if not self._results:
            raise AssertionError(f"FakeRunner: script exhausted at {command!r}")
        return self._results.pop(0)
