"""Evals: a task, its check, its runs, and how they compare with a baseline
(spec hito 8, §1.5 to §1.8, DESIGN §9).

Pure: reading the tasks, copying their repositories and running the checks
belong to the adapters and the application.
"""

import re
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from mharness.domain.limits import TurnLimits
from mharness.domain.money import Usd

# The limits of a task, unless it says otherwise.
TASK_LIMITS = TurnLimits(max_steps=25, timeout=300)
# How much more cost or steps on average counts as a regression.
WORSE_BY = Decimal("0.20")

type Split = Literal["train", "validation"]
# `error`: the run did not finish because of the provider (429, 5xx, network,
# credentials). It says nothing about the agent: not a failure.
type Outcome = Literal["pass", "fail", "error"]


class EvalError(Exception):
    """A task or a baseline that cannot be read; the message says why."""


class Check(BaseModel, frozen=True, extra="forbid"):
    """What must hold after the turn; every part that is set."""

    # A shell command, in the task's copy, that must end with 0.
    command: str | None = None
    # A file of the copy, with these texts and without those.
    file: str | None = None
    contains: list[str] = []
    absent: list[str] = []
    # The final answer: texts it holds, and patterns it matches (regular
    # expressions, without case).
    answer_contains: list[str] = []
    answer_matches: list[str] = []
    # Texts the final answer must not hold.
    answer_absent: list[str] = []

    @model_validator(mode="after")
    def _something(self) -> Self:
        if (self.contains or self.absent) and self.file is None:
            raise ValueError("contains and absent need a file")
        if self.file is not None and not (self.contains or self.absent):
            raise ValueError("a file needs contains or absent")
        answer = self.answer_contains or self.answer_matches or self.answer_absent
        if not (self.command or self.file or answer):
            raise ValueError("a check needs a command, a file or an answer")
        for pattern in self.answer_matches:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid pattern {pattern!r}: {exc}") from None
        return self

    def answer_fails(self, answer: str) -> str | None:
        """Why the answer does not pass, or None."""
        for text in self.answer_contains:
            if text not in answer:
                return f"the answer does not contain {text!r}"
        for pattern in self.answer_matches:
            if not re.search(pattern, answer, re.IGNORECASE):
                return f"the answer does not match {pattern!r}"
        for text in self.answer_absent:
            if text in answer:
                return f"the answer contains {text!r}"
        return None

    def file_fails(self, text: str) -> str | None:
        """Why the file's text does not pass, or None."""
        for wanted in self.contains:
            if wanted not in text:
                return f"{self.file} does not contain {wanted!r}"
        for unwanted in self.absent:
            if unwanted in text:
                return f"{self.file} still contains {unwanted!r}"
        return None


class Task(BaseModel, frozen=True, extra="forbid"):
    # The name of its folder in `evals/tasks/`.
    id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    # Its repository, a folder in `evals/fixtures/`.
    fixture: str = Field(min_length=1)
    split: Split = "train"
    # The tools approved without a person (spec hito 8, §1.2).
    allow: list[str] = []
    limits: TurnLimits = TASK_LIMITS
    check: Check


class TaskRun(BaseModel, frozen=True):
    """One run of one task with one model."""

    task: str
    split: Split
    model: str
    attempt: int
    outcome: Outcome
    # How the turn ended (`RunResult.reason`).
    reason: str
    steps: int
    tool_calls: int
    tool_errors: int
    # Input and output, summed.
    tokens: int
    cost: Usd | None
    duration: float
    # Why it failed, or the provider's error.
    detail: str | None = None


class Stats(BaseModel, frozen=True):
    """Runs of one task, or of several, summed up. The means are over the
    runs that finished (`runs - errors`)."""

    runs: int
    passes: int
    errors: int
    steps: float
    tool_errors: float
    tokens: float
    # None if a run has no known cost.
    cost: Usd | None
    duration: float

    @property
    def finished(self) -> int:
        return self.runs - self.errors

    @property
    def success(self) -> float | None:
        """The share of finished runs that passed."""
        return self.passes / self.finished if self.finished else None


class Baseline(BaseModel, frozen=True):
    """A reference run of the battery with one model, kept in
    `evals/baselines/`. Only numbers: never answers nor traces."""

    date: date
    maha: str
    # The commit it measured, if known.
    commit: str | None
    provider: str
    model: str
    repeat: int
    tasks: dict[str, Stats]
    total: Stats


def stats(runs: Sequence[TaskRun]) -> Stats:
    """The runs given, summed up."""
    done = [run for run in runs if run.outcome != "error"]
    count = len(done) or 1
    costs = [run.cost for run in done]
    cost = (
        None
        if any(c is None for c in costs)
        else sum((c for c in costs if c is not None), Decimal(0)) / count
    )
    return Stats(
        runs=len(runs),
        passes=sum(run.outcome == "pass" for run in runs),
        errors=len(runs) - len(done),
        steps=sum(run.steps for run in done) / count,
        tool_errors=sum(run.tool_errors for run in done) / count,
        tokens=sum(run.tokens for run in done) / count,
        cost=cost,
        duration=sum(run.duration for run in done) / count,
    )


def by_task(runs: Iterable[TaskRun]) -> dict[str, Stats]:
    """The stats of each task, in the order the tasks first appear."""
    grouped: dict[str, list[TaskRun]] = {}
    for run in runs:
        grouped.setdefault(run.task, []).append(run)
    return {task: stats(group) for task, group in grouped.items()}


def combine(parts: Sequence[Stats]) -> Stats:
    """Several tasks' stats as one, each weighted by its finished runs."""
    finished = sum(part.finished for part in parts)
    weight = finished or 1

    def mean(values: Iterable[float]) -> float:
        return sum(values) / weight

    costs = [part.cost for part in parts if part.finished]
    cost = (
        None
        if any(c is None for c in costs)
        else sum(
            (c * part.finished for part in parts if (c := part.cost) is not None),
            Decimal(0),
        )
        / weight
    )
    return Stats(
        runs=sum(part.runs for part in parts),
        passes=sum(part.passes for part in parts),
        errors=sum(part.errors for part in parts),
        steps=mean(part.steps * part.finished for part in parts),
        tool_errors=mean(part.tool_errors * part.finished for part in parts),
        tokens=mean(part.tokens * part.finished for part in parts),
        cost=cost,
        duration=mean(part.duration * part.finished for part in parts),
    )


def compare(current: dict[str, Stats], baseline: Baseline) -> list[str]:
    """The regressions of `current` against `baseline`, over the tasks both
    have (spec hito 8, §1.8): a task that passed every time and now fails,
    a lower success rate, or 20 % more cost or steps on average. Empty if
    none."""
    common = [task for task in current if task in baseline.tasks]
    found = []
    for task in common:
        before, now = baseline.tasks[task], current[task]
        always = before.finished and before.passes == before.finished
        if always and now.finished and now.passes < now.finished:
            found.append(
                f"{task}: passed every time in the baseline, "
                f"now {now.passes}/{now.finished}"
            )
    if not common:
        return found
    before = combine([baseline.tasks[task] for task in common])
    now = combine([current[task] for task in common])
    if (
        before.success is not None
        and now.success is not None
        and now.success < before.success
    ):
        found.append(
            f"success rate: {before.success:.0%} in the baseline, now {now.success:.0%}"
        )
    if before.cost and now.cost is not None and now.cost > before.cost * (1 + WORSE_BY):
        found.append(
            f"cost per run: +{now.cost / before.cost - 1:.0%} "
            f"(${before.cost:.4f} → ${now.cost:.4f})"
        )
    if before.steps and now.steps > before.steps * float(1 + WORSE_BY):
        found.append(
            f"steps per run: +{now.steps / before.steps - 1:.0%} "
            f"({before.steps:.1f} → {now.steps:.1f})"
        )
    return found
