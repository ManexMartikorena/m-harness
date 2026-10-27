"""`MemoryCatalog` follows the port (spec hito 7, §1.4)."""

from datetime import date
from decimal import Decimal

from mharness.domain.catalog import ModelInfo, Prices
from mharness.ports.catalog import ModelCatalog
from tests.fakes.catalog import MemoryCatalog

FLASH = ModelInfo(
    provider="opencode-go",
    model="glm-5.3-flash",
    prices=Prices(
        input=Decimal("0.15"), output=Decimal("0.50"), checked=date(2026, 10, 26)
    ),
)


def test_gives_back_a_known_model() -> None:
    catalog: ModelCatalog = MemoryCatalog([FLASH])

    assert catalog.get("opencode-go", "glm-5.3-flash") == FLASH


def test_the_same_model_on_another_provider_is_another_entry() -> None:
    catalog: ModelCatalog = MemoryCatalog([FLASH])

    assert catalog.get("opencode-zen", "glm-5.3-flash") is None


def test_an_empty_catalog_knows_nothing() -> None:
    assert MemoryCatalog().get("opencode-go", "glm-5.3-flash") is None
