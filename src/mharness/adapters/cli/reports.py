"""Reports printed by the `maha` subcommands (spec hito 8, §1.7, §1.8 and
§1.15)."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TextIO

from mharness.adapters.cli.text import clean_line, usd
from mharness.application.stats import DayModel
from mharness.domain.catalog import ModelInfo
from mharness.domain.evals import Baseline, Stats, TaskRun, by_task, compare, stats

_MARKS = {"pass": "✓", "fail": "✗", "error": "!"}


def run_line(run: TaskRun) -> str:
    """One run of `maha eval`, as it ends."""
    head = f"  {_MARKS[run.outcome]} {run.task} · {run.model} #{run.attempt}"
    if run.outcome == "pass":
        cost = "cost unknown" if run.cost is None else usd(run.cost)
        steps = f"{run.steps} step" + ("" if run.steps == 1 else "s")
        return f"{head} · {steps} · {cost} · {run.duration:.1f} s"
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
        # Wide enough for the total, "48/50" or more.
        passed = max(len("pass"), len(_passed(stats(mine)))) + 2
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
            f"  {'task':<{width}}{'pass':<{passed}}{'steps':<7}{'tool errors':<13}"
            f"{'tokens':<8}{'cost':<9}time",
            file=out,
        )
        for task, row in tasks.items():
            cost = "?" if row.cost is None else usd(row.cost)
            print(
                f"  {task:<{width}}{_passed(row):<{passed}}{row.steps:<7.1f}"
                f"{row.tool_errors:<13.1f}{round(row.tokens):<8}{cost:<9}"
                f"{row.duration:.1f} s",
                file=out,
            )
        splits = {run.split for run in mine}
        if len(splits) > 1:
            for split in ("train", "validation"):
                part = stats([run for run in mine if run.split == split])
                _total(split, part, None, width, passed, out)
        _total("total", stats(mine), _spent(mine), width, passed, out)
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
    label: str,
    row: Stats,
    spent: Decimal | None,
    width: int,
    passed: int,
    out: TextIO,
) -> None:
    rate = "—" if row.success is None else f"{row.success:.0%}"
    line = f"  {label:<{width}}{_passed(row):<{passed}}{rate:<7}"
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


def models_report(
    models: Sequence[ModelInfo], provider: str, *, every: bool, out: TextIO
) -> None:
    """`maha models`: those of `provider`, or `every` one, with their window
    and prices (spec hito 8, §1.15). A model may still work if it is not
    here: the catalog only prices it."""
    shown = sorted(
        (info for info in models if every or info.provider == provider),
        key=lambda info: (info.provider, info.model),
    )
    more = " · maha models --all for every provider"
    if not shown:
        print(f"no models of {clean_line(provider)} in the catalog{more}", file=out)
        return
    rows = [
        [
            clean_line(f"{info.provider}/{info.model}" if every else info.model),
            _context(info.context),
            "?" if info.prices is None else _per_million(info.prices.input),
            "?" if info.prices is None else _per_million(info.prices.output),
            "may train on your data" if info.trains_on_data else "",
        ]
        for info in shown
    ]
    head = ["model", "context", "input $/M", "output $/M", ""]
    widths = [max(len(row[i]) for row in [head, *rows]) for i in range(4)]
    # Three spaces after the name, two between the numbers.
    widths = [widths[0] + 3, *(width + 2 for width in widths[1:])]
    for row in [head, *rows]:
        cells = [cell.ljust(width) for cell, width in zip(row, widths, strict=False)]
        print("".join([*cells, row[4]]).rstrip(), file=out)
    print(file=out)
    count = f"{len(shown)} model" + ("" if len(shown) == 1 else "s")
    if every:
        print(f"{count} · prices per million tokens", file=out)
    else:
        print(
            f"{count} of {clean_line(provider)} · prices per million tokens{more}",
            file=out,
        )


def _context(tokens: int | None) -> str:
    """200k, 1M, 1.5M; ? if unknown."""
    if tokens is None:
        return "?"
    if tokens >= 1_000_000:
        return f"{round(tokens / 1_000_000, 1):g}M"
    return f"{tokens // 1000}k"


def _per_million(price: Decimal) -> str:
    """At least two decimals, and all it has: 0.30, 0.075."""
    text = format(price.normalize(), "f")
    whole, _, decimals = text.partition(".")
    return f"{whole}.{decimals.ljust(2, '0')}"


def stats_report(rows: Sequence[DayModel], *, days: int | None, out: TextIO) -> None:
    """`maha stats`: a row per day and model, and the total. A cost with
    calls of no price is a minimum (≥); with none priced, unknown (?)."""
    if not rows:
        if days is None:
            when = "in the traces"
        else:
            when = "today" if days == 1 else f"in the last {days} days"
        print(f"(no calls to a model {when})", file=out)
        return
    table = [
        [
            f"{row.day:%Y-%m-%d}",
            clean_line(row.model),
            str(row.calls),
            str(row.usage.input_tokens),
            str(row.usage.output_tokens),
            _cost(row.cost, row.calls, row.uncosted),
        ]
        for row in rows
    ]
    calls = sum(row.calls for row in rows)
    total = [
        "total",
        "",
        str(calls),
        str(sum(row.usage.input_tokens for row in rows)),
        str(sum(row.usage.output_tokens for row in rows)),
        _cost(
            sum((row.cost for row in rows), Decimal(0)),
            calls,
            sum(row.uncosted for row in rows),
        ),
    ]
    head = ["day", "model", "calls", "in", "out", "cost"]
    lines = [head, *table, total]
    widths = [max(len(line[i]) for line in lines) for i in range(5)]
    # Two spaces between the columns, three after the model.
    widths = [widths[0] + 2, widths[1] + 3, *(width + 2 for width in widths[2:])]
    for line in lines:
        cells = [cell.ljust(width) for cell, width in zip(line, widths, strict=False)]
        print("".join([*cells, line[5]]), file=out)


def _cost(amount: Decimal, calls: int, uncosted: int) -> str:
    if uncosted == calls:
        return "?"
    return ("≥" if uncosted else "") + usd(amount)
