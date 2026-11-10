"""The titles of the sessions (spec hito 10, §1.12, and §4, tests 11 and
12)."""

from datetime import date
from decimal import Decimal

from mharness.application.titles import (
    MESSAGE_MAX,
    TITLE_TOKENS,
    Title,
    Titler,
    small_model,
)
from mharness.domain.catalog import ModelInfo, Prices
from mharness.domain.errors import ModelUnavailableError
from mharness.domain.model import Usage
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import FakeModelClient, reply

CATALOG = MemoryCatalog(small={"opencode-go": "glm-5.3-flash"})


def test_the_configured_small_model_wins() -> None:
    assert (
        small_model("kimi-k2.7-code", CATALOG, "opencode-go", "m") == "kimi-k2.7-code"
    )


def test_without_one_the_catalogs_for_the_provider() -> None:
    assert small_model(None, CATALOG, "opencode-go", "m") == "glm-5.3-flash"


def test_without_either_the_sessions_own() -> None:
    assert small_model(None, CATALOG, "local", "mi-modelo") == "mi-modelo"


# The titler (spec hito 10, §1.12).


def titler(fake: FakeModelClient, catalog: MemoryCatalog | None = None) -> Titler:
    return Titler(
        fake,
        model="glm-5.3-flash",
        template="Name it: {{message}}",
        catalog=catalog or MemoryCatalog(),
        provider="opencode-go",
    )


async def test_it_reads_at_most_the_start_of_the_first_message() -> None:
    fake = FakeModelClient([reply("Un título")])

    await titler(fake).title("x" * (MESSAGE_MAX + 500))

    [asked] = fake.requests
    assert asked.messages[0].text == "Name it: " + "x" * MESSAGE_MAX
    assert (asked.model, asked.max_tokens, asked.tools) == (
        "glm-5.3-flash",
        TITLE_TOKENS,
        [],
    )


async def test_without_the_providers_cost_the_catalogs_prices() -> None:
    prices = Prices(input=Decimal("1"), output=Decimal("2"), checked=date(2026, 11, 10))
    catalog = MemoryCatalog(
        [ModelInfo(provider="opencode-go", model="glm-5.3-flash", prices=prices)]
    )
    usage = Usage(input_tokens=1_000_000, output_tokens=500_000)
    fake = FakeModelClient([reply("Un título", usage=usage)])

    title = await titler(fake, catalog).title("Hola")

    assert title == Title(
        text="Un título", model="glm-5.3-flash", usage=usage, cost=Decimal("2")
    )


async def test_a_failure_is_told_by_its_kind_and_gives_none() -> None:
    told: list[str] = []
    fake = FakeModelClient([ModelUnavailableError("down, with what was said")])
    subject = Titler(
        fake,
        model="m",
        template="{{message}}",
        catalog=MemoryCatalog(),
        provider="p",
        failed=told.append,
    )

    assert await subject.title("Hola") is None
    assert told == ["ModelUnavailableError"]
