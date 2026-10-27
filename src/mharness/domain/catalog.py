"""What a model costs and what it can hold (DESIGN §6, spec hito 7, §1.4 and
§1.5).

Prices are in USD per million tokens, as providers publish them, and in
`Decimal`: a few tokens at a fraction of a cent must not be rounded away.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from mharness.domain.model import Usage

_MILLION = 1_000_000


class Prices(BaseModel, frozen=True):
    """USD per million tokens of one model on one provider."""

    input: Decimal = Field(ge=0)
    output: Decimal = Field(ge=0)
    # None: billed as input.
    cache_read: Decimal | None = Field(default=None, ge=0)
    cache_write: Decimal | None = Field(default=None, ge=0)
    # When they were checked against the provider's docs: prices change.
    checked: date


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
    OpenAI reports them); `output_tokens` already holds the reasoning.
    """
    cache_read = prices.cache_read if prices.cache_read is not None else prices.input
    cache_write = prices.cache_write if prices.cache_write is not None else prices.input
    cached = usage.cache_read_tokens + usage.cache_write_tokens
    plain = max(usage.input_tokens - cached, 0)
    total = (
        plain * prices.input
        + usage.cache_read_tokens * cache_read
        + usage.cache_write_tokens * cache_write
        + usage.output_tokens * prices.output
    )
    return total / _MILLION
