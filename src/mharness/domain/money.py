"""Amounts of money (spec hito 7, §1.5).

In `Decimal`, never `float`: a few tokens at a fraction of a cent must not
be rounded away.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field, PlainSerializer

# The amounts there can be: from a fraction of a cent per token to far more
# than any session costs. Without bounds, a file that `maha import` takes
# could bring a "1E+5000", written out digit by digit when it is saved or
# shown (audit after hito 9, S4).
SMALLEST = Decimal("1E-12")
LARGEST = Decimal("1E+12")


def _plain(amount: Decimal) -> str:
    # Zero has a sign in Decimal: "-0" says nothing a person can use.
    return "0" if amount.is_zero() else format(amount.normalize(), "f")


def _not_tiny(amount: Decimal) -> Decimal:
    # Compared, never written out: a huge exponent costs nothing here.
    if not amount.is_zero() and amount < SMALLEST:
        raise ValueError(f"an amount in USD is 0 or at least {SMALLEST}")
    return amount


# An amount in USD, never negative nor absurd. In JSON, a string in plain
# notation: exact, unlike a float, and readable, unlike "1.23E-7".
type Usd = Annotated[
    Decimal,
    Field(ge=0, le=LARGEST),
    AfterValidator(_not_tiny),
    PlainSerializer(_plain, return_type=str, when_used="json"),
]
