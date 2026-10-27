"""Port to where the eval tasks, their repositories and the baselines live
(spec hito 8, §1.5 and §1.9, DESIGN §6)."""

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Protocol

from mharness.domain.evals import Baseline, Task


class EvalSuite(Protocol):
    """The battery: its tasks, a fresh copy of a task's repository for each
    run, and the baselines to compare with."""

    async def tasks(self) -> list[Task]:
        """Every task, in order; `EvalError` if one cannot be read."""
        ...

    def workspace(self, task: Task) -> AbstractAsyncContextManager[Path]:
        """A copy of the task's repository, only for this run; it goes away
        on leaving, unless the suite keeps them."""
        ...

    async def read(self, workspace: Path, path: str) -> str | None:
        """A file of the copy as text; None if it is not there."""
        ...

    async def baseline(self, provider: str, model: str) -> Baseline | None:
        """The latest baseline of that model, if there is one."""
        ...

    async def save(self, baseline: Baseline) -> str:
        """Keep a new baseline; where it went."""
        ...
