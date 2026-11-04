"""What a model costs and what it can hold (DESIGN §6, spec hito 7, §1.4 and
§1.5).

Prices are in USD per million tokens, as providers publish them, and in
`Decimal`: a few tokens at a fraction of a cent must not be rounded away.
"""

from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from mharness.domain.model import Usage
from mharness.domain.money import SMALLEST, known

_MILLION = 1_000_000
# The name of an API format: lowercase words joined by hyphens.
API_NAME = r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"
# A family: lowercase words with hyphens, the name of its prompt file.
FAMILY_NAME = API_NAME
# The formats maha speaks; the catalog may name others (spec hito 9, §1.2).
type SpokenApi = Literal["openai-chat", "anthropic"]


def _sensible(rate: Decimal) -> Decimal:
    # One token at a price below this costs less than any amount in USD.
    if not rate.is_zero() and rate < _CHEAPEST:
        raise ValueError(f"a price is 0 or at least {_CHEAPEST} per million")
    return rate


# USD per million tokens: 0, or between these (audit after hito 9, S4).
_CHEAPEST = (SMALLEST * _MILLION).normalize()
type Rate = Annotated[Decimal, Field(ge=0, le=1_000_000), AfterValidator(_sensible)]


class _Rates(BaseModel, frozen=True):
    """USD per million tokens of each kind."""

    input: Rate
    output: Rate
    # None: billed as input.
    cache_read: Rate | None = None
    cache_write: Rate | None = None
    # Writes to the one-hour cache; None: as the other writes.
    cache_write_1h: Rate | None = None


class Tier(_Rates, frozen=True):
    """Prices of a call whose prompt goes past a size (spec hito 7, §1.3)."""

    # Input tokens of the call: the tier starts at above + 1.
    above: int = Field(gt=0)


class Prices(_Rates, frozen=True):
    """What one model costs on one provider."""

    # When they were checked against the provider's docs: prices change.
    checked: date
    # In ascending order of `above`; empty: one price for every size.
    tiers: tuple[Tier, ...] = ()

    @model_validator(mode="after")
    def _tiers_go_up(self) -> Prices:
        pairs = pairwise(tier.above for tier in self.tiers)
        if any(low >= high for low, high in pairs):
            raise ValueError("tiers must be in ascending order of `above`")
        return self


class ModelInfo(BaseModel, frozen=True):
    """What the catalog knows of one model on one provider."""

    provider: str
    model: str
    # Context window, in tokens; None: unknown.
    context: int | None = Field(default=None, gt=0)
    # The API format it speaks ("openai-chat", "anthropic", or one that maha
    # does not speak yet); None: the provider's (spec hito 9, §1.1).
    api: str | None = Field(default=None, pattern=API_NAME)
    # The most tokens one answer may have; None: unknown (spec hito 9, §1.6).
    max_output: int | None = Field(default=None, gt=0)
    # The family of models it belongs to, whose prompt layer it gets
    # ("claude", "glm"); None: none (spec hito 10, §1.3). A name of a file.
    family: str | None = Field(default=None, pattern=FAMILY_NAME)
    # None: unknown, and no cost is shown.
    prices: Prices | None = None
    # The provider may use the conversation to train (ANALISIS §9).
    trains_on_data: bool = False


def add_cost(total: Decimal | None, more: Decimal | None) -> Decimal | None:
    """The sum of two costs; unknown (None) once one of them is, or past
    what an amount in USD can be."""
    return None if total is None or more is None else known(total + more)


def cost(usage: Usage, prices: Prices) -> Decimal:
    """What one call costs, in USD.

    `input_tokens` counts every prompt token, the cached ones included (as
    OpenAI reports them); `output_tokens` already holds the reasoning. Past
    a tier's size, the whole call goes at that tier's prices.
    """
    rates: _Rates = prices
    for tier in prices.tiers:
        if usage.input_tokens > tier.above:
            rates = tier
    cache_read = rates.cache_read if rates.cache_read is not None else rates.input
    cache_write = rates.cache_write if rates.cache_write is not None else rates.input
    hour_write = (
        rates.cache_write_1h if rates.cache_write_1h is not None else cache_write
    )
    cached = usage.cache_read_tokens + usage.cache_write_tokens
    plain = max(usage.input_tokens - cached, 0)
    hour = min(usage.cache_write_1h_tokens, usage.cache_write_tokens)
    total = (
        plain * rates.input
        + usage.cache_read_tokens * cache_read
        + (usage.cache_write_tokens - hour) * cache_write
        + hour * hour_write
        + usage.output_tokens * rates.output
    )
    return total / _MILLION
