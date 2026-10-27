"""Reports printed by the `maha` subcommands (spec hito 8, §1.7, §1.8 and
§1.15)."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TextIO

from mharness.adapters.cli.text import clean_line, usd
from mharness.domain.evals import Baseline, Stats, TaskRun, by_task, compare, stats

_MARKS = {"pass": "✓", "fail": "✗", "error": "!"}


def run_line(run: TaskRun) -> str:
    """One run of `maha eval`, as it ends."""
    head = f"  {_MARKS[run.outcome]} {run.task} · {run.model} #{run.attempt}"
    if run.outcome == "pass":
        cost = "cost unknown" if run.cost is None else usd(run.cost)
        return f"{head} · {run.steps} steps · {cost} · {run.duration:.1f} s"
    detail = clean_line((run.detail or "").splitlines()[0] if run.detail else "")
    if run.outcome == "error":
        return f"{head} · provider: {detail}"
    return f"{head} · {detail}"


def eval_report(
    runs: Sequence[TaskRun], baselines: Mapping[str, Baseline | None], out: TextIO
) -> bool:
    """A table per model, its totals and its regressions against its
    baseline; True if there is any regression."""
    regressed = False
    for model, baseline in baselines.items():
        mine = [run for run in runs if run.model == model]
        tasks = by_task(mine)
        width = max([len("task"), *(len(task) for task in tasks)]) + 3
        print(file=out)
        if baseline is None:
            print(f"{model} · no baseline yet", file=out)
        else:
            commit = f"{baseline.commit}, " if baseline.commit else ""
            print(
                f"{model} · baseline {baseline.date} "
                f"({commit}{baseline.repeat} runs each)",
                file=out,
            )
        print(
            f"  {'task':<{width}}{'pass':<6}{'steps':<7}{'tool errors':<13}"
            f"{'tokens':<8}{'cost':<9}time",
            file=out,
        )
        for task, row in tasks.items():
            cost = "?" if row.cost is None else usd(row.cost)
            print(
                f"  {task:<{width}}{_passed(row):<6}{row.steps:<7.1f}"
                f"{row.tool_errors:<13.1f}{round(row.tokens):<8}{cost:<9}"
                f"{row.duration:.1f} s",
                file=out,
            )
        splits = {run.split for run in mine}
        if len(splits) > 1:
            for split in ("train", "validation"):
                part = stats([run for run in mine if run.split == split])
                _total(split, part, None, width, out)
        _total("total", stats(mine), _spent(mine), width, out)
        errors = sum(run.outcome == "error" for run in mine)
        if errors:
            print(
                f"  provider errors: {errors}, not counted "
                "(--retry-errors runs them again)",
                file=out,
            )
        if baseline is not None:
            for found in compare(tasks, baseline):
                regressed = True
                print(f"  ⚠ {found}", file=out)
    return regressed


def _passed(row: Stats) -> str:
    return f"{row.passes}/{row.finished}"


def _total(
    label: str, row: Stats, spent: Decimal | None, width: int, out: TextIO
) -> None:
    rate = "—" if row.success is None else f"{row.success:.0%}"
    line = f"  {label:<{width}}{_passed(row):<6}{rate:<7}"
    if label == "total":
        line += "cost unknown" if spent is None else f"{usd(spent)} in all"
    print(line.rstrip(), file=out)


def _spent(runs: Sequence[TaskRun]) -> Decimal | None:
    """What the runs that finished cost, all together."""
    total = Decimal(0)
    for run in runs:
        if run.outcome == "error":
            continue
        if run.cost is None:
            return None
        total += run.cost
    return total
