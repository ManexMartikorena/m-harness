"""Amounts of money (spec hito 7, §1.5).

In `Decimal`, never `float`: a few tokens at a fraction of a cent must not
be rounded away.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import Field, PlainSerializer


def _plain(amount: Decimal) -> str:
    # Zero has a sign in Decimal: "-0" says nothing a person can use.
    return "0" if amount.is_zero() else format(amount.normalize(), "f")


# An amount in USD, never negative. In JSON, a string in plain notation:
# exact, unlike a float, and readable, unlike "1.23E-7".
type Usd = Annotated[
    Decimal,
    Field(ge=0),
    PlainSerializer(_plain, return_type=str, when_used="json"),
]
