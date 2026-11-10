"""The titles of the sessions (spec hito 10, §1.12, and §4, tests 11 and
12)."""

from mharness.application.titles import small_model
from tests.fakes.catalog import MemoryCatalog

CATALOG = MemoryCatalog(small={"opencode-go": "glm-5.3-flash"})


def test_the_configured_small_model_wins() -> None:
    assert (
        small_model("kimi-k2.7-code", CATALOG, "opencode-go", "m") == "kimi-k2.7-code"
    )


def test_without_one_the_catalogs_for_the_provider() -> None:
    assert small_model(None, CATALOG, "opencode-go", "m") == "glm-5.3-flash"


def test_without_either_the_sessions_own() -> None:
    assert small_model(None, CATALOG, "local", "mi-modelo") == "mi-modelo"
