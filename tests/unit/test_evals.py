"""The domain of the evals: checks, stats and the comparison with a
baseline (spec hito 8, §1.5 to §1.8)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from mharness.domain.evals import (
    TASK_LIMITS,
    Baseline,
    Check,
    Outcome,
    Stats,
    Task,
    TaskRun,
    by_task,
    combine,
    compare,
    stats,
)


def run(
    task: str = "01",
    outcome: Outcome = "pass",
    *,
    steps: int = 2,
    cost: str | None = "0.001",
    tokens: int = 1000,
) -> TaskRun:
    return TaskRun(
        task=task,
        split="train",
        model="glm-5.3-flash",
        attempt=1,
        outcome=outcome,
        reason="end_turn" if outcome != "error" else "error",
        steps=steps,
        tool_calls=1,
        tool_errors=0,
        tokens=tokens,
        cost=None if cost is None else Decimal(cost),
        duration=2.0,
    )


def baseline(tasks: dict[str, Stats]) -> Baseline:
    return Baseline(
        date=date(2026, 10, 27),
        maha="0.7.1",
        commit="a3eb2c7",
        provider="opencode-go",
        model="glm-5.3-flash",
        repeat=5,
        tasks=tasks,
        total=combine(list(tasks.values())),
    )


# Checks.


def test_a_task_has_default_limits_and_split() -> None:
    task = Task(
        id="01",
        instruction="¿Versión?",
        fixture="tienda",
        check=Check(answer_contains=["1.4.2"]),
    )

    assert (task.split, task.limits, task.allow) == ("train", TASK_LIMITS, [])


@pytest.mark.parametrize(
    "check",
    [
        {},
        {"contains": ["x"]},
        {"file": "a.txt"},
        {"answer_matches": ["("]},
    ],
)
def test_a_check_that_checks_nothing_or_is_broken_is_rejected(
    check: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Check.model_validate(check)


def test_the_answer_is_checked_by_text_and_by_pattern() -> None:
    check = Check(answer_contains=["iva.py"], answer_matches=[r"\b6\b"])

    assert check.answer_fails("Está en src/tienda/iva.py y hay 6") is None
    assert check.answer_fails("Hay 6 ficheros") == (
        "the answer does not contain 'iva.py'"
    )
    # 16 is not 6.
    assert check.answer_fails("iva.py, 16") == r"the answer does not match '\\b6\\b'"


def test_the_file_is_checked_for_what_it_holds_and_lacks() -> None:
    check = Check(file="README.md", contains=["receive"], absent=["recieve"])

    assert check.file_fails("You receive it.") is None
    assert check.file_fails("You recieve it.") == (
        "README.md does not contain 'receive'"
    )
    assert check.file_fails("receive, recieve") == (
        "README.md still contains 'recieve'"
    )


# Stats.


def test_the_means_leave_out_the_runs_the_provider_broke() -> None:
    summary = stats([run(steps=2), run("01", "fail", steps=4), run("01", "error")])

    assert (summary.runs, summary.passes, summary.errors) == (3, 1, 1)
    assert summary.steps == 3
    assert summary.cost == Decimal("0.001")
    assert summary.success == 0.5


def test_a_run_without_cost_makes_the_mean_unknown() -> None:
    assert stats([run(), run(cost=None)]).cost is None


def test_only_errors_have_no_success_rate() -> None:
    assert stats([run(outcome="error")]).success is None


def test_by_task_keeps_the_order() -> None:
    assert list(by_task([run("02"), run("01"), run("02")])) == ["02", "01"]


def test_combine_weights_each_task_by_its_finished_runs() -> None:
    one = stats([run(steps=2)] * 3)
    other = stats([run(steps=6)])

    total = combine([one, other])

    assert (total.runs, total.passes, total.steps) == (4, 4, 3)
    assert total.cost == Decimal("0.001")


# Comparison with the baseline (spec hito 8, §1.8).


def test_no_regression_when_all_stays_the_same() -> None:
    tasks = {"01": stats([run()] * 5), "02": stats([run("02")] * 5)}

    assert compare(tasks, baseline(tasks)) == []


def test_a_task_that_always_passed_and_now_fails_is_a_regression() -> None:
    before = {"01": stats([run()] * 5)}
    now = {"01": stats([run()] * 4 + [run(outcome="fail")])}

    found = compare(now, baseline(before))

    assert "01: passed every time in the baseline, now 4/5" in found
    assert "success rate: 100% in the baseline, now 80%" in found


def test_a_task_that_already_failed_sometimes_only_counts_in_the_total() -> None:
    before = {"01": stats([run()] * 3 + [run(outcome="fail")] * 2)}
    now = {"01": stats([run()] * 3 + [run(outcome="fail")] * 2)}

    assert compare(now, baseline(before)) == []


def test_twenty_percent_more_cost_or_steps_is_a_regression() -> None:
    before = {"01": stats([run(steps=10, cost="0.0010")] * 5)}
    within = {"01": stats([run(steps=12, cost="0.0012")] * 5)}
    beyond = {"01": stats([run(steps=13, cost="0.0013")] * 5)}

    assert compare(within, baseline(before)) == []
    assert compare(beyond, baseline(before)) == [
        "cost per run: +30% ($0.0010 → $0.0013)",
        "steps per run: +30% (10.0 → 13.0)",
    ]


def test_only_the_tasks_both_have_are_compared() -> None:
    # A run of the train split against a full baseline: the validation
    # task that failed in the baseline does not lower its success rate.
    before = {"01": stats([run()] * 5), "09": stats([run("09", "fail")] * 5)}
    now = {"01": stats([run()] * 5)}

    assert compare(now, baseline(before)) == []


def test_provider_errors_are_not_failures() -> None:
    before = {"01": stats([run()] * 5)}
    now = {"01": stats([run()] * 3 + [run(outcome="error")] * 2)}

    assert compare(now, baseline(before)) == []
