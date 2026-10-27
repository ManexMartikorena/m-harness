"""An `EvalSuite` in memory (spec hito 8, §3.1): the repositories are
written to a temporary folder for each run, as the real one copies them."""

import tempfile
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from mharness.domain.evals import Baseline, Task


class MemoryEvalSuite:
    def __init__(
        self,
        tasks: list[Task],
        fixtures: Mapping[str, Mapping[str, str]] | None = None,
        baselines: list[Baseline] | None = None,
    ) -> None:
        self._tasks = tasks
        self._fixtures = fixtures or {}
        self.baselines = list(baselines or [])
        # Every copy handed out, in order.
        self.workspaces: list[Path] = []

    async def tasks(self) -> list[Task]:
        return list(self._tasks)

    @asynccontextmanager
    async def workspace(self, task: Task) -> AsyncIterator[Path]:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            for name, text in self._fixtures.get(task.fixture, {}).items():
                (path / name).parent.mkdir(parents=True, exist_ok=True)
                (path / name).write_text(text, encoding="utf-8")
            self.workspaces.append(path)
            yield path

    async def read(self, workspace: Path, path: str) -> str | None:
        try:
            return (workspace / path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    async def baseline(self, provider: str, model: str) -> Baseline | None:
        found = [
            b for b in self.baselines if (b.provider, b.model) == (provider, model)
        ]
        return max(found, key=lambda b: b.date, default=None)

    async def save(self, baseline: Baseline) -> str:
        self.baselines.append(baseline)
        return f"memory:{baseline.model}"
