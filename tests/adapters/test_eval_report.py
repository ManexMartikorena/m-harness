"""What `maha eval` prints (spec hito 8, §1.7 and §1.8)."""

import io
from datetime import date
from decimal import Decimal

from mharness.adapters.cli.reports import eval_report, run_line
from mharness.domain.evals import Baseline, Outcome, TaskRun, by_task, combine


def run(
    task: str = "01-version",
    outcome: Outcome = "pass",
    *,
    model: str = "glm-5.3-flash",
    split: str = "train",
    attempt: int = 1,
    detail: str | None = None,
    cost: str | None = "0.0004",
) -> TaskRun:
    return TaskRun.model_validate(
        {
            "task": task,
            "split": split,
            "model": model,
            "attempt": attempt,
            "outcome": outcome,
            "reason": "error" if outcome == "error" else "end_turn",
            "steps": 2,
            "tool_calls": 1,
            "tool_errors": 0,
            "tokens": 3120,
            "cost": None if cost is None else Decimal(cost),
            "duration": 2.1,
            "detail": detail,
        }
    )


def test_one_line_per_run_as_it_ends() -> None:
    assert run_line(run()) == (
        "  ✓ 01-version · glm-5.3-flash #1 · 2 steps · $0.0004 · 2.1 s"
    )
    failed = run("06-bug", "fail", detail="the check exited with 1:\nFAILED\nmore")
    assert run_line(failed) == (
        "  ✗ 06-bug · glm-5.3-flash #1 · the check exited with 1:"
    )
    broken = run("03", "error", detail="429 Too Many Requests", cost=None)
    assert (
        run_line(broken)
        == "  ! 03 · glm-5.3-flash #1 · provider: 429 Too Many Requests"
    )


def test_the_report_of_a_model_without_baseline() -> None:
    runs = [
        run(),
        run(attempt=2),
        run("07-renombrar", "fail", split="validation"),
        run("07-renombrar", "error", split="validation", attempt=2, cost=None),
    ]
    out = io.StringIO()

    regressed = eval_report(runs, {"glm-5.3-flash": None}, out)

    assert not regressed
    assert out.getvalue() == (
        "\n"
        "glm-5.3-flash · no baseline yet\n"
        "  task           pass  steps  tool errors  tokens  cost     time\n"
        "  01-version     2/2   2.0    0.0          3120    $0.0004  2.1 s\n"
        "  07-renombrar   0/1   2.0    0.0          3120    $0.0004  2.1 s\n"
        "  train          2/2   100%\n"
        "  validation     0/1   0%\n"
        "  total          2/3   67%    $0.0012 in all\n"
        "  provider errors: 1, not counted (--retry-errors runs them again)\n"
    )


def test_the_report_marks_the_regressions_against_the_baseline() -> None:
    before = by_task([run()] * 5)
    baseline = Baseline(
        date=date(2026, 10, 27),
        maha="0.7.1",
        commit="a3eb2c7",
        provider="opencode-go",
        model="glm-5.3-flash",
        repeat=5,
        tasks=before,
        total=combine(list(before.values())),
    )
    out = io.StringIO()

    regressed = eval_report(
        [run(), run("01-version", "fail", attempt=2)], {"glm-5.3-flash": baseline}, out
    )

    assert regressed
    text = out.getvalue()
    assert "glm-5.3-flash · baseline 2026-10-27 (a3eb2c7, 5 runs each)\n" in text
    assert "  ⚠ 01-version: passed every time in the baseline, now 1/2\n" in text
    assert "  ⚠ success rate: 100% in the baseline, now 50%\n" in text
