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
        "  ✗ 06-bug · glm-5.3-flash #1 · the check exited with 1: more"
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
        "  total          2/3   67%    ≥$0.0012 in all\n"
        "  provider errors: 1, not counted (--retry-errors runs them again)\n"
    )


def test_the_pass_column_fits_the_total() -> None:
    out = io.StringIO()

    eval_report([run(attempt=n) for n in range(1, 11)], {"glm-5.3-flash": None}, out)

    assert "  01-version   10/10  2.0" in out.getvalue()
    assert "  total        10/10  100%" in out.getvalue()


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

    now = [run(attempt=1)] + [run("01-version", "fail", attempt=n) for n in (2, 3, 4)]

    regressed = eval_report(now, {"glm-5.3-flash": baseline}, out)

    assert regressed
    text = out.getvalue()
    assert "glm-5.3-flash · baseline 2026-10-27 (a3eb2c7, 5 runs each)\n" in text
    # With its p (deep audit, I4): 5/5 -> 1/4 is not noise.
    assert "  ⚠ 01-version: 5/5 in the baseline, now 1/4 (p = 0.048)\n" in text


def test_a_drop_within_the_noise_is_said_but_not_marked() -> None:
    # Deep audit (I4): 5/5 -> 4/5 has p = 0.5; it marked a regression.
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
    now = [run(attempt=n) for n in range(1, 5)] + [run("01-version", "fail", attempt=5)]
    out = io.StringIO()

    assert not eval_report(now, {"glm-5.3-flash": baseline}, out)
    assert (
        "  · 01-version: 5/5 in the baseline, now 4/5 (p = 0.5, within the noise)\n"
        in out.getvalue()
    )


def test_an_internal_error_is_not_said_to_be_the_provider() -> None:
    crashed = TaskRun(
        task="02",
        split="train",
        model="m",
        attempt=1,
        outcome="error",
        reason="internal",
        steps=0,
        tool_calls=0,
        tool_errors=0,
        tokens=0,
        cost=None,
        duration=0.0,
        detail="PermissionError: cannot read the fixture",
    )

    assert run_line(crashed) == (
        "  ! 02 · m #1 · internal: PermissionError: cannot read the fixture"
    )


def errored(reason: str, detail: str) -> TaskRun:
    return run("02", "error", detail=detail, cost=None).model_copy(
        update={"reason": reason}
    )


def test_a_failed_check_shows_its_most_useful_line() -> None:
    # Deep audit (I9): the line showed only "the check exited with 1:".
    output = (
        "the check exited with 1:\n"
        "F.\n"
        "Traceback (most recent call last):\n"
        '  File "tests/test_pedidos.py", line 9, in test_volumen\n'
        "AssertionError: 99.0 != 105.0\n"
        "\n"
        "Ran 2 tests in 0.001s\n"
        "\n"
        "FAILED (failures=1)"
    )
    plain = "the check exited with 2:\nusage: notas.py [-h]\nnotas.py: bad option\n"

    assert run_line(run("14", "fail", detail=output)) == (
        "  ✗ 14 · glm-5.3-flash #1 · the check exited with 1: "
        "AssertionError: 99.0 != 105.0"
    )
    assert run_line(run("16", "fail", detail=plain)) == (
        "  ✗ 16 · glm-5.3-flash #1 · the check exited with 2: notas.py: bad option"
    )


def test_each_kind_of_error_says_whose_it_is() -> None:
    assert run_line(errored("credentials", "401 Unauthorized")) == (
        "  ! 02 · glm-5.3-flash #1 · credentials: 401 Unauthorized"
    )
    runs = [
        run(),
        errored("provider", "429"),
        errored("provider", "503"),
        errored("credentials", "401"),
        errored("internal", "OSError: disk full"),
    ]
    out = io.StringIO()

    eval_report(runs, {"glm-5.3-flash": None}, out)

    text = out.getvalue()
    # Deep audit (I9): "provider errors" counted the internal ones too.
    assert "  provider errors: 2, not counted (--retry-errors runs them again)\n" in (
        text
    )
    assert "  credential errors: 1, not counted (check the key)\n" in text
    assert "  internal errors: 1, not counted (a bug of maha: see runs.json)\n" in (
        text
    )


def test_in_all_counts_what_the_runs_with_an_error_cost() -> None:
    # Deep audit (I8): a run that ended in an error was paid all the same.
    paid = errored("provider", "503").model_copy(update={"cost": Decimal("0.0002")})
    out = io.StringIO()

    eval_report([run(), paid], {"glm-5.3-flash": None}, out)

    assert "  total        1/1   100%   $0.0006 in all\n" in out.getvalue()


def test_in_all_is_a_minimum_if_a_run_with_an_error_has_no_cost() -> None:
    out = io.StringIO()

    eval_report(
        [run(), errored("internal", "OSError: disk full")],
        {"glm-5.3-flash": None},
        out,
    )

    assert "  total        1/1   100%   ≥$0.0004 in all\n" in out.getvalue()


def test_with_an_effort_the_baseline_is_shown_but_not_judged() -> None:
    # Deep audit (I7): with --effort, the baseline is of the model's own
    # effort, and hito 9 got a +22 % cost "regression" from it.
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
    # 5/5 -> 0/5: p = 0.004, a regression at the same effort.
    now = [run("01-version", "fail", attempt=n) for n in range(1, 6)]
    out = io.StringIO()

    regressed = eval_report(now, {"glm-5.3-flash": baseline}, out, effort="high")

    assert not regressed
    text = out.getvalue()
    assert "⚠" not in text
    assert "  · 01-version: 5/5 in the baseline, now 0/5 (p = 0.004)" in text
    assert (
        "  · effort high: the baseline ran at the model's own effort, "
        "so the differences are shown, not judged\n"
    ) in text


def test_a_changed_base_prompt_is_said() -> None:
    # Spec hito 10, §1.13: what the baseline measured is not what runs now.
    before = by_task([run()] * 5)
    baseline = Baseline(
        date=date(2026, 11, 4),
        maha="0.9.1",
        commit=None,
        provider="opencode-go",
        model="glm-5.3-flash",
        repeat=5,
        tasks=before,
        total=combine(list(before.values())),
        prompt="aaaaaaaaaaaa",
    )
    note = "  [the base prompt changed since the baseline]"

    for now, said in (("bbbbbbbbbbbb", True), ("aaaaaaaaaaaa", False)):
        out = io.StringIO()
        eval_report(
            [run()] * 5,
            {"glm-5.3-flash": baseline},
            out,
            prompts={"glm-5.3-flash": now},
        )
        assert (note in out.getvalue()) is said
