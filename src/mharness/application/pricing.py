"""What one call to the model cost (spec hito 7, §1.6)."""

from decimal import Decimal

from mharness.domain.catalog import cost
from mharness.domain.model import ModelResponse
from mharness.domain.money import known
from mharness.ports.catalog import ModelCatalog


def call_cost(
    response: ModelResponse, model: str, catalog: ModelCatalog, provider: str
) -> Decimal | None:
    """What one call cost: as the provider says, if it does (exact also
    with prices by the hour or by tier); if not, at the catalog's prices of
    the model that answered, or, if it has none for that name, of the one
    asked (a provider may name it its own way)."""
    if response.cost is not None:
        return response.cost
    for name in (response.model, model):
        info = catalog.get(provider, name)
        if info is not None and info.prices is not None:
            amount = cost(response.usage, info.prices)
            # Past what an amount in USD can be, the counts are a provider's
            # bug: unknown, never a broken turn (deep audit after hito 9, S9).
            # None: a write without a price (audit after hito 10, M4).
            return None if amount is None else known(amount)
    return None
