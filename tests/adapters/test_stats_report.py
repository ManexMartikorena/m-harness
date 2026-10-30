"""`maha stats` (spec hito 8, §1.15)."""

import io
from datetime import date
from decimal import Decimal

from mharness.adapters.cli.reports import stats_report
from mharness.application.stats import DayModel
from mharness.domain.model import Usage


def row(day: int, model: str, calls: int, cost: str, uncosted: int = 0) -> DayModel:
    return DayModel(
        day=date(2026, 10, day),
        model=model,
        calls=calls,
        usage=Usage(input_tokens=1000 * calls, output_tokens=100 * calls),
        cost=Decimal(cost),
        uncosted=uncosted,
    )


def test_a_row_per_day_and_model_and_the_total() -> None:
    out = io.StringIO()

    stats_report(
        [
            row(28, "glm-5.3-flash", 2, "0.002"),
            row(28, "kimi-k2.7-code", 1, "0.010"),
            row(29, "glm-5.3-flash", 3, "0.003"),
        ],
        days=None,
        out=out,
    )

    assert out.getvalue() == (
        "day         model            calls  in    out  cost\n"
        "2026-10-28  glm-5.3-flash    2      2000  200  $0.0020\n"
        "2026-10-28  kimi-k2.7-code   1      1000  100  $0.0100\n"
        "2026-10-29  glm-5.3-flash    3      3000  300  $0.0030\n"
        "total                        6      6000  600  $0.0150\n"
    )


def test_calls_without_a_price_make_the_cost_a_minimum() -> None:
    out = io.StringIO()

    stats_report(
        [row(28, "local", 2, "0", uncosted=2), row(28, "glm", 1, "0.5")],
        days=None,
        out=out,
    )

    lines = out.getvalue().splitlines()
    assert lines[1].endswith("  ?")
    assert lines[-1].endswith("  ≥$0.5000")


def test_without_calls_says_so() -> None:
    out = io.StringIO()
    stats_report([], days=None, out=out)
    assert out.getvalue() == "(no calls to a model in the traces)\n"

    out = io.StringIO()
    stats_report([], days=7, out=out)
    assert out.getvalue() == "(no calls to a model in the last 7 days)\n"
