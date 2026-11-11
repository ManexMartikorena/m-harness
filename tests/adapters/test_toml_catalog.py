"""`TomlCatalog`: the package's catalog and the user's (spec hito 7, §1.3 and
§4.2)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from mharness.adapters.catalog import CatalogError, TomlCatalog, toml_catalog
from mharness.adapters.catalog.toml_catalog import parse
from mharness.domain.catalog import ModelInfo, Prices, Tier
from mharness.ports.catalog import ModelCatalog

CHECKED = date(2026, 10, 27)
# OpenCode's docs, read again in the audit after hito 10.
OPENCODE_CHECKED = date(2026, 11, 11)


@pytest.fixture
def builtin(tmp_path: Path) -> TomlCatalog:
    return TomlCatalog.load(tmp_path / "missing.toml")


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "models.toml"
    path.write_text(text, encoding="utf-8")
    return path


# The catalog in the package.


def test_has_every_model_of_each_provider(builtin: TomlCatalog) -> None:
    # Counted on the providers' docs, 2026-11-11 (audit after hito 10, M4
    # to M7): two more in Go, and in Zen seven more and pulse-alpha-free
    # gone (deprecated on 2026-11-06).
    providers = [info.provider for info in builtin.models()]

    assert providers.count("opencode-go") == 32
    assert providers.count("opencode-zen") == 90
    # Counted on Anthropic's pricing page, 2026-11-03 (spec hito 9, §3.3);
    # without the models of limited access.
    assert providers.count("anthropic") == 14


def test_every_model_has_its_family(builtin: TomlCatalog) -> None:
    # Spec hito 10, §1.3: explicit, never guessed from the id.
    assert [info.model for info in builtin.models() if info.family is None] == []
    families = {(info.provider, info.model): info.family for info in builtin.models()}
    assert families["opencode-go", "glm-5.3-flash"] == "glm"
    assert families["opencode-go", "kimi-k2.7-code"] == "kimi"
    assert families["opencode-go", "claude-haiku-5-5"] == "claude"
    assert families["anthropic", "claude-opus-5-5"] == "claude"


def test_every_model_has_dated_prices(builtin: TomlCatalog) -> None:
    checked = {"anthropic": date(2026, 11, 3)}
    for info in builtin.models():
        # Checked again in the audit after hito 10.
        assert info.prices is not None, info.model
        assert info.prices.checked == checked.get(info.provider, OPENCODE_CHECKED)


def test_a_model_as_the_docs_publish_it(builtin: TomlCatalog) -> None:
    assert builtin.get("opencode-go", "glm-5.3-flash") == ModelInfo(
        provider="opencode-go",
        model="glm-5.3-flash",
        context=1_000_000,
        max_output=131_072,
        family="glm",
        prices=Prices(
            input=Decimal("0.15"),
            output=Decimal("0.50"),
            cache_read=Decimal("0.03"),
            checked=OPENCODE_CHECKED,
        ),
    )


def test_every_anthropic_model_knows_its_longest_answer(builtin: TomlCatalog) -> None:
    # The Messages API needs max_tokens, and one past the model's limit is a
    # 400 (spec hito 9, decision 5).
    anthropic = [
        info
        for info in builtin.models()
        if info.api == "anthropic" or info.provider == "anthropic"
    ]

    # Claude Fable 5.2 in Zen (audit after hito 10).
    assert len(anthropic) == 23 + 14
    assert all(info.max_output for info in anthropic)


def test_a_model_of_anthropic_as_its_pricing_page_publishes_it(
    builtin: TomlCatalog,
) -> None:
    assert builtin.get("anthropic", "claude-opus-5-5") == ModelInfo(
        provider="anthropic",
        model="claude-opus-5-5",
        context=1_000_000,
        max_output=128_000,
        family="claude",
        prices=Prices(
            input=Decimal("4.00"),
            output=Decimal("20.00"),
            cache_read=Decimal("0.20"),
            cache_write=Decimal("5.00"),
            cache_write_1h=Decimal("8.00"),
            checked=date(2026, 11, 3),
        ),
    )


def test_the_format_of_each_model_as_the_provider_serves_it(
    builtin: TomlCatalog,
) -> None:
    # Checked on the providers' docs, 2026-11-03 (spec hito 9, §1.0).
    def api(provider: str, model: str) -> str | None:
        info = builtin.get(provider, model)
        assert info is not None
        return info.api

    assert api("opencode-go", "claude-haiku-5-5") == "anthropic"
    assert api("opencode-go", "minimax-m3") == "anthropic"
    assert api("opencode-go", "gpt-6-luna") == "openai-responses"
    assert api("opencode-go", "gemini-4-argon") == "google"
    # The provider's own format is not written.
    assert api("opencode-go", "glm-5.3-flash") is None


def test_a_model_with_tiers(builtin: TomlCatalog) -> None:
    info = builtin.get("opencode-go", "gpt-6-luna")

    assert info is not None
    assert info.prices is not None
    assert info.prices.tiers == (
        Tier(
            above=272_000,
            input=Decimal("0.20"),
            output=Decimal("0.75"),
            cache_read=Decimal("0.02"),
            cache_write=Decimal("0.25"),
        ),
    )


def test_tiers_cost_more_than_the_base(builtin: TomlCatalog) -> None:
    for info in builtin.models():
        assert info.prices is not None
        for tier in info.prices.tiers:
            assert tier.input > info.prices.input, info.model
            assert tier.output > info.prices.output, info.model


def test_an_hourly_price_takes_the_peak(builtin: TomlCatalog) -> None:
    # DeepSeek V4.1 Flash on Go: 0.15 off-peak, 0.30 peak.
    info = builtin.get("opencode-go", "deepseek-v4.1-flash")

    assert info is not None
    assert info.prices is not None
    assert info.prices.input == Decimal("0.30")


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("opencode-go", "muse-spark-1.3-contributor"),
        ("opencode-go", "muse-spark-1.2-contributor"),
        ("opencode-go", "iceman-contributor-free"),
        ("opencode-zen", "big-pickle"),
        ("opencode-zen", "flint-40b-free"),
        ("opencode-zen", "mimo-v2.6-flash-free"),
        ("opencode-zen", "nemotron-3-ultra-free"),
        ("opencode-zen", "nemotron-3.5-lightning-free"),
        ("opencode-zen", "nemotron-3.5-super-vl-free"),
        ("opencode-zen", "iceman-free"),
        ("opencode-zen", "inkling-2-small-free"),
    ],
)
def test_models_that_train_on_the_data(
    builtin: TomlCatalog, provider: str, model: str
) -> None:
    info = builtin.get(provider, model)

    assert info is not None
    assert info.trains_on_data


def test_only_those_train_on_the_data(builtin: TomlCatalog) -> None:
    training = [info for info in builtin.models() if info.trains_on_data]

    assert len(training) == 11


def test_an_unknown_model_is_none(builtin: TomlCatalog) -> None:
    catalog: ModelCatalog = builtin

    assert catalog.get("opencode-go", "modelo-que-no-existe") is None
    assert catalog.get("ollama", "glm-5.3-flash") is None


# The user's file.


def test_the_user_file_wins_and_adds(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        """
[providers.ollama]
checked = 2026-10-27

[models."opencode-go/glm-5.3-flash"]
input = 0.10
output = 0.40
checked = 2026-11-01

[models."ollama/qwen-local"]
context = 32_768
input = 0
output = 0
""",
    )

    catalog = TomlCatalog.load(path)

    flash = catalog.get("opencode-go", "glm-5.3-flash")
    assert flash is not None
    assert flash.prices is not None
    # The whole model is replaced: no context nor cache price from the package.
    assert flash.context is None
    assert flash.prices == Prices(
        input=Decimal("0.10"), output=Decimal("0.40"), checked=date(2026, 11, 1)
    )
    local = catalog.get("ollama", "qwen-local")
    assert local is not None
    assert local.prices is not None
    assert local.prices.input == 0
    assert local.prices.checked == CHECKED
    assert catalog.get("opencode-go", "kimi-k3") is not None


def test_a_user_model_without_prices_has_no_cost(tmp_path: Path) -> None:
    path = write(tmp_path, '[models."ollama/qwen-local"]\ncontext = 32_768\n')

    info = TomlCatalog.load(path).get("ollama", "qwen-local")

    assert info == ModelInfo(provider="ollama", model="qwen-local", context=32_768)


def test_a_user_model_says_its_api_and_longest_answer(tmp_path: Path) -> None:
    # Spec hito 9, §1.1.
    path = write(
        tmp_path, '[models."local/claude-x"]\napi = "anthropic"\nmax_output = 64_000\n'
    )

    info = TomlCatalog.load(path).get("local", "claude-x")

    assert info == ModelInfo(
        provider="local", model="claude-x", api="anthropic", max_output=64_000
    )


def test_a_user_model_says_its_family(tmp_path: Path) -> None:
    # Spec hito 10, §1.3: a model of the user's own gets a prompt layer.
    path = write(tmp_path, '[models."local/mi-modelo"]\nfamily = "qwen"\n')

    info = TomlCatalog.load(path).get("local", "mi-modelo")

    assert info == ModelInfo(provider="local", model="mi-modelo", family="qwen")


def test_each_provider_has_its_small_model(builtin: TomlCatalog) -> None:
    # Spec hito 10, §1.12: the cheapest that the evals measure; in Zen, the
    # paid one, never the free one that may train on the data.
    assert builtin.small_model("opencode-go") == "glm-5.3-flash"
    assert builtin.small_model("opencode-zen") == "glm-5.3-flash"
    assert builtin.small_model("anthropic") == "claude-haiku-5-5"
    assert builtin.small_model("local") is None
    zen = builtin.get("opencode-zen", "glm-5.3-flash")
    assert zen is not None
    assert not zen.trains_on_data


def test_the_user_names_a_small_model(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "[providers.opencode-go]\nchecked = 2026-11-10\n"
        'small_model = "kimi-k2.7-code"\n',
    )

    assert TomlCatalog.load(path).small_model("opencode-go") == "kimi-k2.7-code"


def test_a_small_model_not_in_the_catalog_is_an_error(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "[providers.opencode-go]\nchecked = 2026-11-10\n"
        'small_model = "glm-5.3-flahs"\n',
    )

    with pytest.raises(CatalogError, match=r"'glm-5\.3-flahs' is not in the catalog"):
        TomlCatalog.load(path)


def test_a_price_for_the_hour_cache(tmp_path: Path) -> None:
    # Spec hito 9, decision 9.
    path = write(
        tmp_path,
        '[models."local/m"]\ninput = 1\noutput = 5\ncache_write = 1.25\n'
        "cache_write_1h = 2\nchecked = 2026-11-03\n",
    )

    info = TomlCatalog.load(path).get("local", "m")

    assert info is not None
    assert info.prices is not None
    assert info.prices.cache_write_1h == Decimal(2)


def test_a_model_id_may_hold_a_slash(tmp_path: Path) -> None:
    path = write(tmp_path, '[models."openrouter/anthropic/claude-x"]\n')

    assert TomlCatalog.load(path).get("openrouter", "anthropic/claude-x") is not None


def test_an_unreadable_user_file_is_an_error(tmp_path: Path) -> None:
    folder = tmp_path / "models.toml"
    folder.mkdir()

    with pytest.raises(CatalogError, match="cannot read"):
        TomlCatalog.load(folder)


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("[models", "invalid TOML"),
        (
            '[models."ollama/x"]\nimput = 0.1\n',
            # The key always quoted: it may hold dots (audit of hito 7).
            r'models\."ollama/x"\.imput: unknown field',
        ),
        ('[models."qwen-local"]\n', 'models."qwen-local": the key must be'),
        ('[models."/x"]\n', "the key must be"),
        ('[models."ollama/"]\n', "the key must be"),
        (
            '[models."ollama/x"]\ninput = 0.1\nchecked = 2026-10-27\n',
            "input and output go together",
        ),
        ('[models."ollama/x"]\ninput = 0.1\noutput = 0.2\n', "prices need a date"),
        (
            '[models."ollama/x"]\n[[models."ollama/x".tiers]]\n'
            "above = 10\ninput = 1\noutput = 1\n",
            "tiers without input and output",
        ),
        (
            '[models."ollama/x"]\ninput = -0.1\noutput = 0.2\nchecked = 2026-10-27\n',
            r'models."ollama/x"\.input: Input should be greater than or equal to 0',
        ),
        (
            '[models."ollama/x"]\ninput = 1\noutput = 1\nchecked = 2026-10-27\n'
            '[[models."ollama/x".tiers]]\nabove = 500\ninput = 2\noutput = 2\n'
            '[[models."ollama/x".tiers]]\nabove = 100\ninput = 3\noutput = 3\n',
            "ascending order",
        ),
        ('[models."ollama/x"]\ncontext = 0\n', "greater than 0"),
        (
            "[providers.ollama]\nsource = 'x'\n",
            r'providers\."ollama"\.checked: Field required',
        ),
        (
            # Which tier is wrong (audit of hito 7).
            '[models."ollama/x"]\ninput = 1\noutput = 1\nchecked = 2026-10-27\n'
            '[[models."ollama/x".tiers]]\nabove = 100\ninput = 2\noutput = 2\n'
            '[[models."ollama/x".tiers]]\nabove = 500\ninput = -3\noutput = 3\n',
            r'models\."ollama/x"\.tiers\.1\.input: Input should be greater',
        ),
        (
            '[models."ollama/x"]\ninput = "1.5"\noutput = 1\nchecked = 2026-10-27\n',
            r'models\."ollama/x"\.input: .*number, not text',
        ),
        ('[models."ollama/x"]\napi = "Anthropic"\n', r'models\."ollama/x"\.api'),
        ('[models."ollama/x"]\nmax_output = 0\n', "greater than 0"),
        # Deep audit after hito 9 (M10): true was taken as 1.
        ('[models."ollama/x"]\ncontext = true\n', r'models\."ollama/x"\.context'),
        ('[models."ollama/x"]\nmax_output = true\n', r'models\."ollama/x"\.max_output'),
        ('[models." ollama/x"]\n', "no spaces"),
        # The family names a file of prompts/families/ (spec hito 10, §1.3).
        ('[models."ollama/x"]\nfamily = "../x"\n', "family"),
        ('[models."ollama/x"]\nfamily = "Claude"\n', "family"),
        ('[models."ollama/qwen local"]\n', "no spaces"),
    ],
)
def test_a_broken_user_file_says_what_and_where(
    tmp_path: Path, text: str, problem: str
) -> None:
    path = write(tmp_path, text)

    with pytest.raises(CatalogError, match=problem) as caught:
        TomlCatalog.load(path)

    assert str(path) in str(caught.value)


def test_parse_names_its_source() -> None:
    with pytest.raises(CatalogError, match="the built-in catalog"):
        parse("[models", "the built-in catalog")


def test_a_user_file_that_is_not_utf8_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "models.toml"
    path.write_bytes(b'[models."ollama/\xff"]\n')

    with pytest.raises(CatalogError, match="not valid UTF-8") as caught:
        TomlCatalog.load(path)

    assert str(path) in str(caught.value)


def test_a_built_in_catalog_that_cannot_be_read_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A broken install: an error that says so, not a traceback (audit of
    # hito 7).
    monkeypatch.setattr(toml_catalog, "PACKAGED", "missing.toml")

    with pytest.raises(CatalogError, match="cannot read the built-in catalog"):
        TomlCatalog.load(tmp_path / "missing.toml")


def test_a_user_price_needs_its_own_date(tmp_path: Path) -> None:
    # The built-in [providers.opencode-go] date is not the day the user
    # checked their price.
    path = write(tmp_path, '[models."opencode-go/glm-5.3"]\ninput = 1\noutput = 2\n')

    with pytest.raises(CatalogError, match="prices need a date"):
        TomlCatalog.load(path)
