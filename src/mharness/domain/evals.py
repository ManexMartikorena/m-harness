"""Evals: a task, its check, its runs, and how they compare with a baseline
(spec hito 8, §1.5 to §1.8, DESIGN §9).

Pure: reading the tasks, copying their repositories and running the checks
belong to the adapters and the application.
"""

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from math import comb, sqrt
from pathlib import PurePosixPath
from statistics import fmean, variance
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from mharness.domain.environment import CREDENTIAL_SUFFIXES
from mharness.domain.limits import TurnLimits
from mharness.domain.money import Usd

# The limits of a task, unless it says otherwise.
TASK_LIMITS = TurnLimits(max_steps=25, timeout=300)
# How much more cost or steps on average counts as a regression, beyond
# the noise (deep audit, I4).
WORSE_BY = Decimal("0.20")
# A drop in success is a regression if the noise explains it less than
# once in 20 times (one-sided p, deep audit, I4).
ALPHA = 0.05
# The runs of each task a baseline needs: fewer are noise (spec hito 8,
# decision 3; deep audit, I13).
BASELINE_REPEAT = 5
# The one-sided 95 % quantile of the normal law: the lower bound of a mean.
Z_95 = 1.645

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
    # The test files of the fixture the task asks the agent to write or
    # change: the check sees the agent's version. Every other test file is
    # put back as the fixture has it before the check, so a test the agent
    # changed neither fails right code nor passes a cheat (deep audit, I1).
    own_tests: list[str] = []

    @model_validator(mode="after")
    def _something(self) -> Self:
        if (self.contains or self.absent) and self.file is None:
            raise ValueError("contains and absent need a file")
        if self.file is not None and not (self.contains or self.absent):
            raise ValueError("a file needs contains or absent")
        answer = self.answer_contains or self.answer_matches or self.answer_absent
        if not (self.command or self.file or answer):
            raise ValueError("a check needs a command, a file or an answer")
        for name in self.own_tests:
            if not is_test_file(name):
                raise ValueError(f"own_tests: {name!r} is not a test file")
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


def is_test_file(path: str) -> bool:
    """Whether a file of a fixture, by its path from the fixture's root, is
    a test: under `tests/` or `test/`, `test_*.py`, `*_test.py` or
    `conftest.py` (deep audit, I1)."""
    parts = PurePosixPath(path).parts
    name = parts[-1] if parts else ""
    return (
        any(part in ("tests", "test") for part in parts[:-1])
        or (name.startswith("test_") and name.endswith(".py"))
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


# What a check command may see of maha's own variables: enough to find
# python3 and speak the user's language, nothing of the user's home (deep
# audit, I5). Until the sandbox of hito 15, a mitigation: the check runs
# code the model wrote, on this machine.
CHECK_VARIABLES = frozenset({"PATH", "LANG", "LANGUAGE", "TZ"})


def check_env(env: Mapping[str, str], home: str) -> dict[str, str]:
    """The variables of a check command: those of `CHECK_VARIABLES` and
    `LC_*` that `env` has, with `home`, an empty folder of the run, as its
    HOME and TMPDIR. No XDG folder, no credential, no SSH agent."""
    kept = {
        name: value
        for name, value in env.items()
        if (name in CHECK_VARIABLES or name.startswith("LC_"))
        and not name.upper().endswith(CREDENTIAL_SUFFIXES)
    }
    return {**kept, "HOME": home, "TMPDIR": home}


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
    # The test files of the fixture the run had changed, and its check saw
    # as the fixture has them (deep audit, I1).
    restored: list[str] = []


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


class Finding(BaseModel, frozen=True):
    """What the comparison with a baseline found: a `regression` (⚠), or
    a difference worth saying that the noise explains."""

    text: str
    regression: bool


def fisher_worse(
    before_passes: int, before_runs: int, now_passes: int, now_runs: int
) -> float:
    """The one-sided p of Fisher's exact test that the success rate got
    worse: with no change at all, the chance of a drop at least this large
    (deep audit, I4). Given how many runs passed in all, the passes of the
    baseline follow a hypergeometric law; p is the chance of it holding
    `before_passes` or more. 5/5 -> 4/5 is 0.5; 5/5 -> 1/5, 6/252."""
    passed = before_passes + now_passes
    runs = before_runs + now_runs
    ways = sum(
        comb(passed, held) * comb(runs - passed, before_runs - held)
        for held in range(before_passes, min(before_runs, passed) + 1)
    )
    # Exact integers to the end: Python divides big ones exactly.
    return min(1.0, ways / comb(runs, before_runs))


def _lower_bound(groups: Sequence[Sequence[float]]) -> float | None:
    """The lower bound, at 95 % and one-sided, of the mean of the task
    means, each from its runs: the mean minus 1.645 standard errors of a
    stratified mean, `sqrt(sum(s_t² / n_t)) / T`. Only the noise within
    each task counts: both sides run the same tasks. Deterministic, with
    no resampling; None if a task has fewer than 2 runs, whose noise cannot
    be told. The baseline keeps only means, so its own noise is left out:
    the gate is conservative by the side of the baseline it can see."""
    if not groups or any(len(group) < 2 for group in groups):
        return None
    mean = sum(fmean(group) for group in groups) / len(groups)
    error = sqrt(sum(variance(group) / len(group) for group in groups))
    return mean - Z_95 * error / len(groups)


def _judge_rate(label: str, before: Stats, now: Stats) -> Finding:
    p = fisher_worse(before.passes, before.finished, now.passes, now.finished)
    regression = p < ALPHA
    noise = "" if regression else ", within the noise"
    return Finding(text=f"{label} (p = {p:.2g}{noise})", regression=regression)


def _judge_mean(
    name: str,
    before: float,
    groups: Sequence[Sequence[float]],
    shown: Callable[[float], str],
) -> Finding | None:
    """A mean per run, cost or steps, against the baseline's: a regression
    only if even its lower bound is `WORSE_BY` over the baseline."""
    now = sum(fmean(group) for group in groups) / len(groups)
    limit = before * float(1 + WORSE_BY)
    if not before or now <= limit:
        return None
    head = f"{name} per run: +{now / before - 1:.0%} ({shown(before)} → {shown(now)}"
    bound = _lower_bound(groups)
    if bound is None:
        return Finding(
            text=f"{head}; not judged: needs 2 runs of each task)", regression=False
        )
    if bound > limit:
        return Finding(text=f"{head}, at least {shown(bound)})", regression=True)
    return Finding(
        text=f"{head}, at least {shown(bound)}: within the noise)", regression=False
    )


def compare(runs: Sequence[TaskRun], baseline: Baseline) -> list[Finding]:
    """What `runs` show against `baseline`, over the tasks both have (spec
    hito 8, §1.8, with the rule of the maintainer of 2026-11-03, deep audit,
    I4: the old one marked the noise of 5 runs):

    - a task, or the total of the runs pooled, whose success dropped, with
      the one-sided p of Fisher's exact test: a regression if p < 0.05;
    - cost or steps per run (the mean of the task means) over 20 % more
      than the baseline's: a regression only if the lower bound of their
      95 % interval is over it too (`_lower_bound`);
    - a task where no run finished, and a cost that can no longer be
      compared (audit of hito 8): regressions;
    - the tasks the baseline does not have, named (deep audit, I13).

    Never re-runs anything. Empty if nothing changed for the worse."""
    current = by_task(runs)
    common = [task for task in current if task in baseline.tasks]
    found = []
    # Said, not hidden: their runs are in the table, not in the gate (deep
    # audit, I13).
    if new := [task for task in current if task not in baseline.tasks]:
        found.append(
            Finding(
                text=f"not in the baseline, not compared: {', '.join(new)}",
                regression=False,
            )
        )
    for task in common:
        before, now = baseline.tasks[task], current[task]
        if before.finished and now.runs and not now.finished:
            # Nothing to compare: what broke may be the change itself.
            found.append(
                Finding(
                    text=f"{task}: no run finished, every one ended in an error "
                    f"({now.errors}/{now.runs})",
                    regression=True,
                )
            )
        if _dropped(before, now):
            label = (
                f"{task}: {before.passes}/{before.finished} in the baseline, "
                f"now {now.passes}/{now.finished}"
            )
            found.append(_judge_rate(label, before, now))
    if not common:
        return found
    before = combine([baseline.tasks[task] for task in common])
    now = combine([current[task] for task in common])
    if _dropped(before, now):
        # Fisher on the runs of every task pooled.
        label = (
            f"success rate: {before.passes / before.finished:.0%} in the baseline, "
            f"now {now.passes / now.finished:.0%}"
        )
        found.append(_judge_rate(label, before, now))
    # The tasks both finished, each with its runs that finished.
    both = [
        task
        for task in common
        if baseline.tasks[task].finished and current[task].finished
    ]
    done = {
        task: [run for run in runs if run.task == task and run.outcome != "error"]
        for task in both
    }
    if not both:
        return found
    costs_before = [baseline.tasks[task].cost for task in both]
    if all(cost is not None for cost in costs_before):
        cost_before = float(sum(c for c in costs_before if c is not None)) / len(both)
        if any(run.cost is None for task in both for run in done[task]):
            if cost_before:
                found.append(
                    Finding(
                        text=f"cost per run: unknown now (a run had no price), "
                        f"${cost_before:.4f} in the baseline",
                        regression=True,
                    )
                )
        else:
            groups = [[float(run.cost or 0) for run in done[task]] for task in both]
            if (cost := _judge_mean("cost", cost_before, groups, _dollars)) is not None:
                found.append(cost)
    steps_before = sum(baseline.tasks[task].steps for task in both) / len(both)
    groups = [[float(run.steps) for run in done[task]] for task in both]
    if (steps := _judge_mean("steps", steps_before, groups, _one)) is not None:
        found.append(steps)
    return found


def _dropped(before: Stats, now: Stats) -> bool:
    return (
        before.success is not None
        and now.success is not None
        and now.success < before.success
    )


def _dollars(amount: float) -> str:
    return f"${amount:.4f}"


def _one(amount: float) -> str:
    return f"{amount:.1f}"
