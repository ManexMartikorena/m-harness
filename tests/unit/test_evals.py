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
    Finding,
    Outcome,
    Stats,
    Task,
    TaskRun,
    by_task,
    combine,
    compare,
    fisher_worse,
    is_test_file,
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


def test_the_answer_can_be_checked_for_what_it_must_not_say() -> None:
    check = Check(answer_contains=["calcular_iva"], answer_absent=["resumen"])

    assert check.answer_fails("calcular_iva") is None
    assert Check(answer_absent=["x"]).answer_fails("y") is None
    assert check.answer_fails("calcular_iva, resumen") == (
        "the answer contains 'resumen'"
    )


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


# Comparison with the baseline (spec hito 8, §1.8; deep audit, I4: a
# regression is what the noise of 5 runs hardly explains).


def runs_of(task: str, passes: int, fails: int = 0, **kwargs: object) -> list[TaskRun]:
    return [run(task, **kwargs)] * passes + [run(task, "fail", **kwargs)] * fails  # type: ignore[arg-type]


def regressions(found: list[Finding]) -> list[str]:
    return [f.text for f in found if f.regression]


def notes(found: list[Finding]) -> list[str]:
    return [f.text for f in found if not f.regression]


@pytest.mark.parametrize(
    ("before", "now", "p"),
    [
        ((5, 5), (4, 5), 0.5),
        ((5, 5), (1, 5), 6 / 252),
        ((5, 5), (5, 5), 1.0),
        ((94, 100), (86, 100), 0.0485),
        ((94, 100), (87, 100), 0.0732),
    ],
)
def test_fisher_exact_one_sided_with_known_values(
    before: tuple[int, int], now: tuple[int, int], p: float
) -> None:
    assert fisher_worse(*before, *now) == pytest.approx(p, abs=1e-4)


def test_fisher_is_one_sided_a_rise_is_never_worse() -> None:
    assert fisher_worse(1, 5, 5, 5) == 1.0


def test_no_regression_when_all_stays_the_same() -> None:
    now = runs_of("01", 5) + runs_of("02", 5)

    assert compare(now, baseline(by_task(now))) == []


def test_one_failure_in_five_is_noise_not_a_regression() -> None:
    # 5/5 -> 4/5: p = 0.5. The old rule marked it.
    before = by_task(runs_of("01", 5))

    found = compare(runs_of("01", 4, 1), baseline(before))

    assert regressions(found) == []
    assert notes(found) == [
        "01: 5/5 in the baseline, now 4/5 (p = 0.5, within the noise)",
        "success rate: 100% in the baseline, now 80% (p = 0.5, within the noise)",
    ]


def test_a_task_that_drops_far_is_a_regression_with_its_p() -> None:
    # 5/5 -> 1/5: p = 6/252 ≈ 0.024 < 0.05.
    before = by_task(runs_of("01", 5) + runs_of("02", 5))
    now = runs_of("01", 1, 4) + runs_of("02", 5)

    found = compare(now, baseline(before))

    # The total, 10/10 -> 6/10: p ≈ 0.043.
    assert regressions(found) == [
        "01: 5/5 in the baseline, now 1/5 (p = 0.024)",
        "success rate: 100% in the baseline, now 60% (p = 0.043)",
    ]
    assert notes(found) == []


def test_the_total_is_judged_on_the_pooled_runs() -> None:
    # 94/100 -> 86/100 is just a regression; 94/100 -> 87/100 is not.
    before = by_task(runs_of("01", 94, 6))

    assert regressions(compare(runs_of("01", 86, 14), baseline(before))) == [
        "01: 94/100 in the baseline, now 86/100 (p = 0.049)",
        "success rate: 94% in the baseline, now 86% (p = 0.049)",
    ]
    assert regressions(compare(runs_of("01", 87, 13), baseline(before))) == []


def test_twenty_percent_more_cost_or_steps_is_a_regression() -> None:
    # The same in every run: no noise, the bound is the mean itself.
    before = by_task(runs_of("01", 5, steps=10, cost="0.0010"))
    within = runs_of("01", 5, steps=12, cost="0.0012")
    beyond = runs_of("01", 5, steps=13, cost="0.0013")

    assert compare(within, baseline(before)) == []
    assert regressions(compare(beyond, baseline(before))) == [
        "cost per run: +30% ($0.0010 → $0.0013, at least $0.0013)",
        "steps per run: +30% (10.0 → 13.0, at least 13.0)",
    ]


def test_more_steps_within_the_noise_are_said_but_not_marked() -> None:
    # Mean 13 (+30 %), but runs of 6, 13 and 20: the lower bound of 95 %,
    # 13 - 1.645 * 7 / sqrt(5) ≈ 7.9, is not 20 % over 10.
    before = by_task(runs_of("01", 5, steps=10))
    now = [run("01", steps=6)] * 2 + [run("01", steps=20)] * 2 + [run("01", steps=13)]

    found = compare(now, baseline(before))

    assert regressions(found) == []
    assert notes(found) == [
        "steps per run: +30% (10.0 → 13.0, at least 7.9: within the noise)"
    ]


def test_with_one_run_of_a_task_more_steps_are_not_judged() -> None:
    before = by_task(runs_of("01", 5, steps=10))

    found = compare([run("01", steps=13)], baseline(before))

    assert regressions(found) == []
    assert notes(found) == [
        "steps per run: +30% (10.0 → 13.0; not judged: needs 2 runs of each task)"
    ]


def test_a_task_that_already_failed_sometimes_and_stays_is_no_regression() -> None:
    now = runs_of("01", 3, 2)

    assert compare(now, baseline(by_task(now))) == []


def test_only_the_tasks_both_have_are_compared() -> None:
    # A run of the train split against a full baseline: the validation
    # task that failed in the baseline does not lower its success rate.
    before = by_task(runs_of("01", 5) + runs_of("09", 0, 5))

    assert compare(runs_of("01", 5), baseline(before)) == []


def test_provider_errors_are_not_failures() -> None:
    before = by_task(runs_of("01", 5))
    now = runs_of("01", 3) + [run(outcome="error")] * 2

    assert compare(now, baseline(before)) == []


def test_a_task_with_no_run_finished_is_a_regression() -> None:
    # Audit of hito 8: a change that makes the provider refuse every call
    # (a broken tool schema) left nothing to compare and passed the gate.
    before = by_task(runs_of("01", 5) + runs_of("02", 5))
    now = [run(outcome="error")] * 5 + runs_of("02", 5)

    assert regressions(compare(now, baseline(before))) == [
        "01: no run finished, every one ended in an error (5/5)"
    ]


def test_a_cost_that_cannot_be_compared_is_said() -> None:
    # Audit of hito 8: it was skipped in silence.
    before = by_task(runs_of("01", 5))

    assert regressions(compare(runs_of("01", 5, cost=None), baseline(before))) == [
        "cost per run: unknown now (a run had no price), $0.0010 in the baseline"
    ]


# The fixture's tests (deep audit, I1).


@pytest.mark.parametrize(
    ("path", "test"),
    [
        ("tests/test_pedidos.py", True),
        ("tests/__init__.py", True),
        ("test_texto.py", True),
        ("pkg/thing_test.py", True),
        ("conftest.py", True),
        ("src/tienda/pedidos.py", False),
        ("testing.py", False),
        ("README.md", False),
    ],
)
def test_which_files_of_a_fixture_are_tests(path: str, test: bool) -> None:
    assert is_test_file(path) is test


def test_own_tests_must_be_tests() -> None:
    with pytest.raises(ValidationError, match="not a test file"):
        Check(command="true", own_tests=["inventory.py"])
