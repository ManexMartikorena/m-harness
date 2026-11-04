"""Amounts in USD (spec hito 7, §1.5; audit after hito 9, S4)."""

from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from mharness.domain.money import Usd

USD: TypeAdapter[Decimal] = TypeAdapter(Usd)


@pytest.mark.parametrize(
    "text", ["0", "-0", "0.000000123", "0.0008", "12.5", "1E-12", "1000000000000"]
)
def test_an_amount_a_session_can_cost(text: str) -> None:
    amount = USD.validate_json(f'"{text}"')

    assert USD.validate_json(USD.dump_json(amount)) == amount


@pytest.mark.parametrize(
    "text",
    [
        "-0.5",
        "Infinity",
        "NaN",
        # Written out digit by digit, a huge exponent fills the memory: an
        # imported file can bring one.
        "1E+50",
        "1E-50",
        "1000000000001",
        "9E-13",
    ],
)
def test_an_amount_no_session_costs_is_refused(text: str) -> None:
    with pytest.raises(ValidationError):
        USD.validate_json(f'"{text}"')


def test_many_digits_of_a_normal_amount_are_kept() -> None:
    # A price read from a float has many digits, not a huge exponent.
    price = Decimal("0.1499999999999999944488848768742172978818416595458984375")
    amount = price * 1234 / 1_000_000

    assert USD.validate_python(amount) == amount
