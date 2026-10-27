"""`TomlEvalSuite`: the battery in a folder, `evals/` in the repository of
maha (spec hito 8, §1.5 and §1.9).

```
evals/
├── tasks/<id>/task.toml     # one task; its folder is its id
├── fixtures/<name>/         # the repositories the tasks work on
└── baselines/*.json         # the reference runs, only numbers
```

Each run gets a copy of its repository in a temporary folder: the fixture
is never touched, and runs in parallel never see each other's changes.
"""

import asyncio
import shutil
import tempfile
import tomllib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mharness.domain.evals import TASK_LIMITS, Baseline, EvalError, Task
from mharness.domain.limits import TurnLimits


class TomlEvalSuite:
    def __init__(self, root: Path, *, keep: bool = False) -> None:
        self._root = root
        # Keep the copies after each run, to look at them.
        self._keep = keep

    async def tasks(self) -> list[Task]:
        return await asyncio.to_thread(self._tasks)

    @asynccontextmanager
    async def workspace(self, task: Task) -> AsyncIterator[Path]:
        # Resolved: the tools and the session name it the same way.
        folder = await asyncio.to_thread(
            lambda: Path(tempfile.mkdtemp(prefix="maha-eval-")).resolve()
        )
        copy = folder / task.fixture
        try:
            await asyncio.to_thread(
                shutil.copytree,
                self._root / "fixtures" / task.fixture,
                copy,
                symlinks=True,
            )
            yield copy
        finally:
            if not self._keep:
                await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)

    async def read(self, workspace: Path, path: str) -> str | None:
        def read() -> str | None:
            try:
                return (workspace / path).read_text(encoding="utf-8", errors="replace")
            except FileNotFoundError, IsADirectoryError:
                return None

        return await asyncio.to_thread(read)

    async def baseline(self, provider: str, model: str) -> Baseline | None:
        return await asyncio.to_thread(self._baseline, provider, model)

    async def save(self, baseline: Baseline) -> str:
        return await asyncio.to_thread(self._save, baseline)

    def _tasks(self) -> list[Task]:
        folder = self._root / "tasks"
        found = sorted(folder.glob("*/task.toml")) if folder.is_dir() else []
        if not found:
            raise EvalError(f"no tasks in {folder}")
        return [self._task(path) for path in found]

    def _task(self, path: Path) -> Task:
        name = path.parent.name
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            raise EvalError(f"task {name}: cannot read {path}: {exc}") from None
        except tomllib.TOMLDecodeError as exc:
            raise EvalError(f"task {name}: invalid TOML: {exc}") from None
        if "id" in data:
            raise EvalError(f"task {name}: id: unknown field (the folder is the id)")
        try:
            data["limits"] = _limits(data.get("limits", {}))
            task = Task.model_validate({**data, "id": name})
        except ValidationError as exc:
            raise EvalError(f"task {name}: {_problems(exc)}") from None
        except EvalError as exc:
            raise EvalError(f"task {name}: {exc}") from None
        if not (self._root / "fixtures" / task.fixture).is_dir():
            raise EvalError(f"task {name}: no fixture {task.fixture!r}")
        return task

    def _baseline(self, provider: str, model: str) -> Baseline | None:
        found = []
        for path in sorted((self._root / "baselines").glob("*.json")):
            try:
                baseline = Baseline.model_validate_json(path.read_bytes())
            except (OSError, ValidationError) as exc:
                raise EvalError(f"cannot read the baseline {path}: {exc}") from None
            if (baseline.provider, baseline.model) == (provider, model):
                found.append((baseline.date, path.name, baseline))
        return max(found, key=lambda item: item[:2])[2] if found else None

    def _save(self, baseline: Baseline) -> str:
        folder = self._root / "baselines"
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{baseline.date}-{baseline.provider}-{baseline.model}".replace("/", "_")
        path = folder / f"{stem}.json"
        number = 1
        while path.exists():
            number += 1
            path = folder / f"{stem}-{number}.json"
        path.write_text(baseline.model_dump_json(indent=2) + "\n", encoding="utf-8")
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return str(path)


def _limits(table: Any) -> TurnLimits:
    """A task's `[limits]`: what it sets, on top of the tasks' defaults."""
    if not isinstance(table, dict):
        raise EvalError("limits: must be a table")
    unknown = set(table) - set(TurnLimits.model_fields)
    if unknown:
        raise EvalError(f"limits.{sorted(unknown)[0]}: unknown field")
    return TurnLimits.model_validate({**TASK_LIMITS.model_dump(), **table})


def _problems(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'task'}: "
        + ("unknown field" if error["type"] == "extra_forbidden" else error["msg"])
        for error in exc.errors()
    )
