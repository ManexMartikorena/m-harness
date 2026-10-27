"""What a model costs and what it can hold (DESIGN §6, spec hito 7, §1.4 and
§1.5).

Prices are in USD per million tokens, as providers publish them, and in
`Decimal`: a few tokens at a fraction of a cent must not be rounded away.
"""

from datetime import date
from decimal import Decimal
from itertools import pairwise

from pydantic import BaseModel, Field, model_validator

from mharness.domain.model import Usage

_MILLION = 1_000_000


class _Rates(BaseModel, frozen=True):
    """USD per million tokens of each kind."""

    input: Decimal = Field(ge=0)
    output: Decimal = Field(ge=0)
    # None: billed as input.
    cache_read: Decimal | None = Field(default=None, ge=0)
    cache_write: Decimal | None = Field(default=None, ge=0)


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
    # None: unknown, and no cost is shown.
    prices: Prices | None = None
    # The provider may use the conversation to train (ANALISIS §9).
    trains_on_data: bool = False


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
    cached = usage.cache_read_tokens + usage.cache_write_tokens
    plain = max(usage.input_tokens - cached, 0)
    total = (
        plain * rates.input
        + usage.cache_read_tokens * cache_read
        + usage.cache_write_tokens * cache_write
        + usage.output_tokens * rates.output
    )
    return total / _MILLION
