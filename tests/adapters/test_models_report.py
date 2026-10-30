"""`maha models` (spec hito 8, §1.15)."""

import io
from datetime import date
from decimal import Decimal

from mharness.adapters.cli.reports import models_report
from mharness.domain.catalog import ModelInfo, Prices

CHECKED = date(2026, 10, 27)


def model(
    provider: str,
    name: str,
    *,
    context: int | None = 200_000,
    prices: tuple[str, str] | None = ("0.30", "1.20"),
    trains: bool = False,
) -> ModelInfo:
    return ModelInfo(
        provider=provider,
        model=name,
        context=context,
        prices=None
        if prices is None
        else Prices(
            input=Decimal(prices[0]), output=Decimal(prices[1]), checked=CHECKED
        ),
        trains_on_data=trains,
    )


CATALOG = [
    model("opencode-go", "kimi-k2.7-code", context=262_144, prices=("0.6", "2.5")),
    model("opencode-go", "glm-5.3-flash", prices=("0.075", "0.3")),
    model("opencode-zen", "glm-5.3", trains=True),
    model("opencode-go", "nuevo", context=None, prices=None),
]


def test_the_models_of_the_provider_in_order() -> None:
    out = io.StringIO()

    models_report(CATALOG, "opencode-go", every=False, out=out)

    assert out.getvalue() == (
        "model            context  input $/M  output $/M\n"
        "glm-5.3-flash    200k     0.075      0.30\n"
        "kimi-k2.7-code   262k     0.60       2.50\n"
        "nuevo            ?        ?          ?\n"
        "\n"
        "3 models of opencode-go · prices per million tokens · maha models --all "
        "for every provider\n"
    )


def test_every_provider_with_all_and_the_training_warning() -> None:
    out = io.StringIO()

    models_report(CATALOG, "opencode-go", every=True, out=out)

    lines = out.getvalue().splitlines()
    assert lines[0].startswith("model ")
    assert lines[1].startswith("opencode-go/glm-5.3-flash ")
    assert lines[4] == (
        "opencode-zen/glm-5.3         200k     0.30       1.20        "
        "may train on your data"
    )
    assert lines[-1] == "4 models · prices per million tokens"


def test_a_provider_without_models_says_so() -> None:
    out = io.StringIO()

    models_report(CATALOG, "local", every=False, out=out)

    assert out.getvalue() == (
        "no models of local in the catalog · maha models --all for every provider\n"
    )


def test_names_from_the_user_catalog_are_clean() -> None:
    out = io.StringIO()

    models_report([model("local", "m\x1b[2J")], "local", every=False, out=out)

    assert "m\\x1b[2J" in out.getvalue()
