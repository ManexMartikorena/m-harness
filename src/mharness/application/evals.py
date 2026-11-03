"""Run the eval battery: each task, with each model, as many times as asked,
several at once; then check each run (spec hito 8, §1.5 to §1.9).

A run goes through `run_once()`, as `maha -p` does. Its check is run by this
code, never by the model: the answer, a file of the copy, and a command in
the copy. A run the provider broke (429, 5xx, network, credentials) is an
`error`, not a failure: it says nothing about the agent. A request the
provider rejected, or an answer maha cannot read, is a failure: it may be a
bug of maha (deep audit, I2).
"""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Literal

from mharness.application.headless import RunResult, TurnBroke, run_once
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
        # Each run as it ends, its last try: a retry replaces the error it
        # repeats (review of the audit of hito 8).
        self._finished: dict[tuple[str, str, int], TaskRun] = {}

    @property
    def finished(self) -> list[TaskRun]:
        """The runs that ended so far, one per run: what Ctrl+C keeps."""
        return list(self._finished.values())

    def _ended(self, run: TaskRun, on_run: Callable[[TaskRun], None]) -> None:
        self._finished[run.model, run.task, run.attempt] = run
        on_run(run)

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
                run = await self._safe(task, model, attempt)
            self._ended(run, on_run)
            # Only what may pass if repeated: a bug of maha or a rejected
            # key comes back, and the retry is paid (review of the audit of
            # hito 8; deep audit, I2).
            if run.outcome == "error" and run.reason == "provider" and retry_errors:
                async with limit:
                    run = await self._safe(task, model, attempt)
                self._ended(run, on_run)
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

    async def _safe(self, task: Task, model: str, attempt: int) -> TaskRun:
        """`_one()`, where a bug or the disk failing is an `error` of this
        run alone, with the reason `internal`: one run must not take the
        battery, and its paid calls, with it (audit of hito 8)."""
        try:
            return await self._one(task, model, attempt)
        except Exception as exc:
            return TaskRun(
                task=task.id,
                split=task.split,
                model=model,
                attempt=attempt,
                outcome="error",
                reason="internal",
                steps=0,
                tool_calls=0,
                tool_errors=0,
                tokens=0,
                cost=None,
                duration=0.0,
                detail=f"{type(exc).__name__}: {exc}",
            )

    async def _one(self, task: Task, model: str, attempt: int) -> TaskRun:
        async with self._suite.workspace(task) as path:
            try:
                async with self._open_run(task, model, path) as conversation:
                    result = await run_once(conversation, task.instruction)
            except TurnBroke as exc:
                # With what the run spent, already paid.
                spent = exc.result
                return _run(
                    task, model, attempt, spent, "error", spent.error, reason="internal"
                )
            if result.reason == "error":
                return _failed(task, model, attempt, result)
            try:
                detail = await self.check(task.check, path, result.text)
            except Exception as exc:
                # With what the run spent, already paid (review of the
                # audit of hito 8).
                broke = f"{type(exc).__name__}: {exc}"
                return _run(
                    task, model, attempt, result, "error", broke, reason="internal"
                )
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


# What a failed call says, when it is maha's own: a failure.
_MAHAS = {
    "request": "the provider rejected the request of maha",
    "response": "maha could not read the answer",
}


def _failed(task: Task, model: str, attempt: int, result: RunResult) -> TaskRun:
    """A run whose call to the model failed: an `error` if the provider
    broke it, a `fail` if maha did (deep audit, I2)."""
    failure = result.failure or "provider"
    if failure in _MAHAS:
        detail = f"{_MAHAS[failure]}: {result.error}"
        return _run(task, model, attempt, result, "fail", detail, reason=failure)
    return _run(task, model, attempt, result, "error", result.error, reason=failure)


def _run(
    task: Task,
    model: str,
    attempt: int,
    result: RunResult,
    outcome: Outcome,
    detail: str | None,
    *,
    reason: str | None = None,
) -> TaskRun:
    return TaskRun(
        task=task.id,
        split=task.split,
        model=model,
        attempt=attempt,
        outcome=outcome,
        reason=reason or result.reason,
        steps=result.steps,
        tool_calls=result.tool_calls,
        tool_errors=result.tool_errors,
        tokens=result.usage.input_tokens + result.usage.output_tokens,
        cost=result.cost,
        duration=result.duration,
        detail=detail,
    )
