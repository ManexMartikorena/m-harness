"""Prices, model info and cost (spec hito 7, §1.4, §1.5 and §4.1.1)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from mharness.domain.catalog import ModelInfo, Prices, Tier, cost
from mharness.domain.model import Usage

CHECKED = date(2026, 10, 26)
# glm-5.3-flash on OpenCode Go (spec hito 7, §1.1), plus a made-up write price.
PRICES = Prices(
    input=Decimal("0.15"),
    output=Decimal("0.50"),
    cache_read=Decimal("0.03"),
    cache_write=Decimal("0.20"),
    checked=CHECKED,
)


def test_input_and_output_per_million() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=2_000_000)

    assert cost(usage, PRICES) == Decimal("1.15")


def test_cache_read_is_inside_input_at_its_own_price() -> None:
    usage = Usage(input_tokens=1_000_000, cache_read_tokens=400_000)

    # 600 000 at 0.15 and 400 000 at 0.03.
    assert cost(usage, PRICES) == Decimal("0.102")


def test_cache_read_without_its_price_is_billed_as_input() -> None:
    prices = Prices(input=Decimal("0.15"), output=Decimal("0.50"), checked=CHECKED)
    usage = Usage(input_tokens=1_000_000, cache_read_tokens=400_000)

    assert cost(usage, prices) == Decimal("0.15")


def test_cache_write_is_inside_input_at_its_own_price() -> None:
    usage = Usage(input_tokens=1_000_000, cache_write_tokens=500_000)

    # 500 000 at 0.15 and 500 000 at 0.20.
    assert cost(usage, PRICES) == Decimal("0.175")


def test_cache_write_without_its_price_is_billed_as_input() -> None:
    prices = Prices(input=Decimal("0.15"), output=Decimal("0.50"), checked=CHECKED)
    usage = Usage(input_tokens=1_000_000, cache_write_tokens=500_000)

    assert cost(usage, prices) == Decimal("0.15")


def test_reasoning_is_already_inside_output() -> None:
    plain = Usage(input_tokens=100, output_tokens=286)
    reasoning = Usage(input_tokens=100, output_tokens=286, reasoning_tokens=190)

    assert cost(reasoning, PRICES) == cost(plain, PRICES)


def test_cost_is_exact() -> None:
    # 41 tokens at 0.003 per million: a float would not give this back.
    prices = Prices(input=Decimal("0.003"), output=Decimal(0), checked=CHECKED)

    assert cost(Usage(input_tokens=41), prices) == Decimal("0.000000123")


def test_more_cache_than_input_never_goes_negative() -> None:
    # A provider that counts the cache apart from the input.
    usage = Usage(input_tokens=10, cache_read_tokens=1_000_000)

    assert cost(usage, PRICES) == Decimal("0.03")


def test_no_tokens_cost_nothing() -> None:
    assert cost(Usage(), PRICES) == 0


# GPT 6 Luna on OpenCode Go (2026-10-27), plus a made-up third tier.
TIERED = Prices(
    input=Decimal("0.10"),
    output=Decimal("0.50"),
    cache_read=Decimal("0.01"),
    checked=CHECKED,
    tiers=(
        Tier(above=272_000, input=Decimal("0.20"), output=Decimal("0.75")),
        Tier(above=500_000, input=Decimal("0.40"), output=Decimal("1.00")),
    ),
)


def test_up_to_the_threshold_the_base_prices_apply() -> None:
    usage = Usage(input_tokens=272_000, output_tokens=1_000)

    # 272 000 at 0.10 and 1 000 at 0.50.
    assert cost(usage, TIERED) == Decimal("0.0277")


def test_above_the_threshold_the_whole_call_goes_to_the_tier() -> None:
    usage = Usage(input_tokens=272_001, output_tokens=1_000)

    # 272 001 at 0.20 and 1 000 at 0.75.
    assert cost(usage, TIERED) == Decimal("0.0551502")


def test_the_highest_tier_passed_applies() -> None:
    usage = Usage(input_tokens=600_000)

    assert cost(usage, TIERED) == Decimal("0.24")


def test_a_tier_without_cache_prices_bills_the_cache_as_its_input() -> None:
    # The base cache_read (0.01) does not carry over to the tier.
    usage = Usage(input_tokens=300_000, cache_read_tokens=100_000)

    assert cost(usage, TIERED) == Decimal("0.06")


def test_tiers_must_go_up() -> None:
    with pytest.raises(ValidationError, match="ascending"):
        Prices(
            input=Decimal(1),
            output=Decimal(1),
            checked=CHECKED,
            tiers=(
                Tier(above=500_000, input=Decimal(2), output=Decimal(2)),
                Tier(above=272_000, input=Decimal(3), output=Decimal(3)),
            ),
        )


def test_tiers_must_not_repeat_a_threshold() -> None:
    with pytest.raises(ValidationError, match="ascending"):
        Prices(
            input=Decimal(1),
            output=Decimal(1),
            checked=CHECKED,
            tiers=(
                Tier(above=272_000, input=Decimal(2), output=Decimal(2)),
                Tier(above=272_000, input=Decimal(3), output=Decimal(3)),
            ),
        )


def test_a_tier_needs_a_positive_threshold() -> None:
    with pytest.raises(ValidationError):
        Tier(above=0, input=Decimal(1), output=Decimal(1))


def test_prices_reject_a_negative_price() -> None:
    with pytest.raises(ValidationError):
        Prices(input=Decimal("-0.15"), output=Decimal("0.50"), checked=CHECKED)


def test_model_info_defaults() -> None:
    info = ModelInfo(provider="opencode-go", model="glm-5.3-flash")

    assert info.context is None
    assert info.prices is None
    assert info.trains_on_data is False


def test_model_info_is_immutable() -> None:
    info = ModelInfo(provider="opencode-go", model="glm-5.3-flash", prices=PRICES)

    with pytest.raises(ValidationError):
        info.trains_on_data = True  # type: ignore[misc]
