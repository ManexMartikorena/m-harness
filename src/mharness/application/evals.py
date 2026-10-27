"""Run the eval battery: each task, with each model, as many times as asked,
several at once; then check each run (spec hito 8, §1.5 to §1.9).

A run goes through `run_once()`, as `maha -p` does. Its check is run by this
code, never by the model: the answer, a file of the copy, and a command in
the copy. A run the provider broke (`reason == "error"`) is an `error`, not
a failure: it says nothing about the agent.
"""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

from mharness.application.headless import RunResult, run_once
from mharness.application.sessions import Conversation
from mharness.domain.evals import Check, EvalError, Outcome, Task, TaskRun
from mharness.ports.commands import CommandRunner
from mharness.ports.evals import EvalSuite

# Opens the conversation of one run: its model, its tools on the copy and
# its approvals (`AllowList` with the task's `allow`). bootstrap builds it.
type OpenRun = Callable[[Task, str, Path], AbstractAsyncContextManager[Conversation]]

# Seconds a check command may take.
CHECK_TIME_LIMIT = 60.0
# What a failed check command shows of its output: the end, where the
# error usually is.
CHECK_OUTPUT_CHARS = 800


def choose(
    tasks: Sequence[Task],
    split: Literal["train", "validation", "all"],
    only: Sequence[str] = (),
) -> list[Task]:
    """The tasks of `split`, or only those named; `EvalError` for a name
    that is not a task."""
    unknown = set(only) - {task.id for task in tasks}
    if unknown:
        raise EvalError(f"no task {sorted(unknown)[0]!r}")
    return [
        task
        for task in tasks
        if (split == "all" or task.split == split) and (not only or task.id in only)
    ]


class Evaluator:
    def __init__(
        self,
        suite: EvalSuite,
        open_run: OpenRun,
        runner: CommandRunner,
        env: Mapping[str, str],
    ) -> None:
        self._suite = suite
        self._open_run = open_run
        self._runner = runner
        # The variables of the check command, as for any command of maha.
        self._env = env

    async def run(
        self,
        tasks: Sequence[Task],
        models: Sequence[str],
        *,
        repeat: int = 1,
        jobs: int = 4,
        retry_errors: bool = False,
        on_run: Callable[[TaskRun], None] = lambda run: None,
    ) -> list[TaskRun]:
        """Every run, by model, task and attempt. At most `jobs` at once.
        With `retry_errors`, the runs the provider broke run once more.
        `on_run` hears of each run as it ends."""
        limit = asyncio.Semaphore(jobs)

        async def one(task: Task, model: str, attempt: int) -> TaskRun:
            async with limit:
                run = await self._one(task, model, attempt)
            on_run(run)
            if run.outcome == "error" and retry_errors:
                async with limit:
                    run = await self._one(task, model, attempt)
                on_run(run)
            return run

        return list(
            await asyncio.gather(
                *(
                    one(task, model, attempt)
                    for model in models
                    for task in tasks
                    for attempt in range(1, repeat + 1)
                )
            )
        )

    async def _one(self, task: Task, model: str, attempt: int) -> TaskRun:
        async with self._suite.workspace(task) as path:
            async with self._open_run(task, model, path) as conversation:
                result = await run_once(conversation, task.instruction)
            if result.reason == "error":
                return _run(task, model, attempt, result, "error", result.error)
            detail = await self.check(task.check, path, result.text)
        outcome: Outcome = "pass" if detail is None else "fail"
        return _run(task, model, attempt, result, outcome, detail)

    async def check(self, check: Check, path: Path, answer: str) -> str | None:
        """Why a run, with the copy at `path` and its final `answer`, does
        not pass `check`; None if it passes."""
        if (why := check.answer_fails(answer)) is not None:
            return why
        if check.file is not None:
            text = await self._suite.read(path, check.file)
            if text is None:
                return f"{check.file} does not exist"
            if (why := check.file_fails(text)) is not None:
                return why
        if check.command is not None:
            done = await self._runner.run(
                check.command, cwd=path, time_limit=CHECK_TIME_LIMIT, env=self._env
            )
            if done.timed_out:
                return f"the check took more than {CHECK_TIME_LIMIT:.0f} s"
            if done.exit_code != 0:
                output = done.output.strip()[-CHECK_OUTPUT_CHARS:]
                return f"the check exited with {done.exit_code}:\n{output}"
        return None


def _run(
    task: Task,
    model: str,
    attempt: int,
    result: RunResult,
    outcome: Outcome,
    detail: str | None,
) -> TaskRun:
    return TaskRun(
        task=task.id,
        split=task.split,
        model=model,
        attempt=attempt,
        outcome=outcome,
        reason=result.reason,
        steps=result.steps,
        tool_calls=result.tool_calls,
        tool_errors=result.tool_errors,
        tokens=result.usage.input_tokens + result.usage.output_tokens,
        cost=result.cost,
        duration=result.duration,
        detail=detail,
    )
