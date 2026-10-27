"""The model catalog from TOML files (spec hito 7, §1.3).

Two files, same format: `models.toml` in this package, and the user's
`~/.config/maha/models.toml`, which wins model by model. Never a project
file: a repository must not change what `maha` says a model costs.

```toml
[providers.opencode-go]
checked = 2026-10-27          # default date of that provider's prices
source = "https://opencode.ai/docs/go/"

[models."opencode-go/gpt-6-luna"]
context = 1_050_000
input = 0.10                  # USD per million tokens
output = 0.50

[[models."opencode-go/gpt-6-luna".tiers]]
above = 272_000
input = 0.20
output = 0.75
```

Read once, at start-up: synchronous, like the configuration.
"""

import tomllib
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ValidationError

from mharness.domain.catalog import ModelInfo, Prices, Tier


class CatalogError(Exception):
    """A catalog file cannot be used; the message says which and why."""


class _Provider(BaseModel, extra="forbid"):
    checked: date
    source: str | None = None


class _Tier(BaseModel, extra="forbid"):
    above: int
    input: Decimal
    output: Decimal
    cache_read: Decimal | None = None
    cache_write: Decimal | None = None


class _Model(BaseModel, extra="forbid"):
    context: int | None = None
    # Both or neither: a model without prices is known, but has no cost.
    input: Decimal | None = None
    output: Decimal | None = None
    cache_read: Decimal | None = None
    cache_write: Decimal | None = None
    # Overrides the provider's date.
    checked: date | None = None
    tiers: list[_Tier] = []
    trains_on_data: bool = False


class _File(BaseModel, extra="forbid"):
    providers: dict[str, _Provider] = {}
    models: dict[str, _Model] = {}


class TomlCatalog:
    """A `ModelCatalog` read from the package's file and the user's."""

    def __init__(self, models: Iterable[ModelInfo]) -> None:
        self._models = {(info.provider, info.model): info for info in models}

    @classmethod
    def load(cls, user_file: Path) -> TomlCatalog:
        """The package's catalog, with the user's file on top if it exists.
        Raises `CatalogError`."""
        packaged = resources.files(__package__) / "models.toml"
        models = parse(packaged.read_text(encoding="utf-8"), "the built-in catalog")
        try:
            text = user_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls(models)
        except OSError as exc:
            raise CatalogError(f"cannot read {user_file}: {exc.strerror}") from None
        except UnicodeDecodeError:
            raise CatalogError(f"{user_file} is not valid UTF-8") from None
        # Later entries win: the user's replace whole models.
        return cls([*models, *parse(text, str(user_file))])

    def get(self, provider: str, model: str) -> ModelInfo | None:
        return self._models.get((provider, model))

    def models(self) -> list[ModelInfo]:
        """Every model, in file order."""
        return list(self._models.values())


def parse(text: str, source: str) -> list[ModelInfo]:
    """The models in one catalog file. Raises `CatalogError`, naming
    `source`."""
    try:
        data = tomllib.loads(text, parse_float=Decimal)
    except tomllib.TOMLDecodeError as exc:
        raise CatalogError(f"invalid TOML in {source}: {exc}") from None
    try:
        file = _File.model_validate(data)
    except ValidationError as exc:
        raise _invalid(source, _problems(exc, prefix="")) from None
    models: list[ModelInfo] = []
    for key, model in file.models.items():
        try:
            models.append(_info(key, model, file.providers))
        # A ValidationError is also a ValueError: it goes first.
        except ValidationError as exc:
            raise _invalid(source, _problems(exc, prefix=f'models."{key}"')) from None
        except ValueError as exc:
            raise _invalid(source, f'  models."{key}": {exc}') from None
    return models


def _info(key: str, model: _Model, providers: dict[str, _Provider]) -> ModelInfo:
    provider, _, name = key.partition("/")
    if not provider or not name:
        raise ValueError('the key must be "provider/model"')
    return ModelInfo(
        provider=provider,
        model=name,
        context=model.context,
        prices=_prices(model, providers.get(provider)),
        trains_on_data=model.trains_on_data,
    )


def _prices(model: _Model, provider: _Provider | None) -> Prices | None:
    if model.input is None and model.output is None:
        if model.tiers:
            raise ValueError("tiers without input and output")
        return None
    if model.input is None or model.output is None:
        raise ValueError("input and output go together")
    checked = model.checked or (provider.checked if provider else None)
    if checked is None:
        raise ValueError(
            "prices need a date: `checked` in the model or in [providers.<name>]"
        )
    return Prices(
        input=model.input,
        output=model.output,
        cache_read=model.cache_read,
        cache_write=model.cache_write,
        checked=checked,
        tiers=tuple(Tier(**tier.model_dump()) for tier in model.tiers),
    )


def _invalid(source: str, problems: str) -> CatalogError:
    return CatalogError(f"invalid model catalog in {source}:\n{problems}")


def _problems(exc: ValidationError, *, prefix: str) -> str:
    lines = []
    for error in exc.errors():
        where = ".".join(str(part) for part in (prefix, *error["loc"]) if part != "")
        what = "unknown field" if error["type"] == "extra_forbidden" else error["msg"]
        lines.append(f"  {where}: {what}")
    return "\n".join(lines)
