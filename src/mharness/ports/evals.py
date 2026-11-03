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

    async def home(self, workspace: Path) -> Path:
        """An empty folder of the run of `workspace`, out of the copy, that
        goes away with it: the HOME of its check (deep audit, I5)."""
        ...

    async def restore_tests(self, task: Task, workspace: Path) -> list[str]:
        """Put the test files of the task's fixture back in the copy as the
        fixture has them, but those of `task.check.own_tests`; the paths of
        those the run had changed (deep audit, I1)."""
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
