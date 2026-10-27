"""Load and validate the configuration (spec hito 2, §1.10).

Three levels, the later one winning for `provider` and `model`; of each
limit of the turn, the stricter one wins (spec hito 8, §3.2):

1. built-in providers, in this module;
2. the user's file, `$XDG_CONFIG_HOME/maha/config.toml`;
3. the project's file, `.maha/config.toml` in the working directory.

Providers (URL and key variable) can only be declared by the user: a project
file is untrusted input, and could send the user's key to another server.

Start-up plumbing: only `mharness.bootstrap` uses it, once, before the core.
"""

import tomllib
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from mharness.domain.limits import TurnLimits

PROJECT_FILE = Path(".maha") / "config.toml"
DEFAULT_PROVIDER = "opencode-go"


class ConfigError(Exception):
    """The configuration is missing or wrong; the message says what to do."""


class ProviderSettings(BaseModel, frozen=True, extra="forbid"):
    """How to reach one provider."""

    # The only API format until hito 9 adds "anthropic".
    api: Literal["openai-chat"] = "openai-chat"
    base_url: str = Field(min_length=1)
    # Name of the environment variable that holds the key; None sends no key.
    api_key_env: str | None = None
    session_header: str | None = None


BUILTIN_PROVIDERS: Mapping[str, ProviderSettings] = {
    "opencode-go": ProviderSettings(
        base_url="https://opencode.ai/inference/go/openai/v1",
        api_key_env="OPENCODE_API_KEY",
        session_header="x-opencode-session",
    ),
    "opencode-zen": ProviderSettings(
        base_url="https://opencode.ai/inference/openai/v1",
        api_key_env="OPENCODE_API_KEY",
        session_header="x-opencode-session",
    ),
}


class Settings(BaseModel, frozen=True):
    """Everything `maha` needs to start a conversation."""

    provider_name: str
    provider: ProviderSettings
    model: str
    limits: TurnLimits = TurnLimits()
    # Kept out of repr, so it never lands in a log or a traceback.
    api_key: str | None = Field(default=None, repr=False)


class _Limits(BaseModel, extra="forbid"):
    """`[limits]`: each one, if the file sets it."""

    max_steps: int | None = Field(default=None, ge=1)
    max_cost: Decimal | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout: float | None = Field(default=None, gt=0)


class _ProjectFile(BaseModel, extra="forbid"):
    provider: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    limits: _Limits = _Limits()


class _UserFile(_ProjectFile):
    providers: dict[str, ProviderSettings] = {}


def user_config_path(env: Mapping[str, str]) -> Path:
    """`$XDG_CONFIG_HOME/maha/config.toml`, by default under `~/.config`."""
    return _config_dir(env) / "config.toml"


def user_catalog_path(env: Mapping[str, str]) -> Path:
    """`$XDG_CONFIG_HOME/maha/models.toml`: the user's prices, which win over
    the built-in ones (spec hito 7, §1.3). Never a project's."""
    return _config_dir(env) / "models.toml"


def _config_dir(env: Mapping[str, str]) -> Path:
    xdg = env.get("XDG_CONFIG_HOME", "")
    # The XDG spec says to ignore relative paths.
    base = Path(xdg) if Path(xdg).is_absolute() else _home() / ".config"
    return base / "maha"


def data_dir(env: Mapping[str, str]) -> Path:
    """`$XDG_DATA_HOME/maha`, by default under `~/.local/share`: sessions,
    and later traces and memory (DESIGN §7, spec hito 6, §1.1)."""
    xdg = env.get("XDG_DATA_HOME", "")
    # The XDG spec says to ignore relative paths.
    base = Path(xdg) if Path(xdg).is_absolute() else _home() / ".local" / "share"
    return base / "maha"


def state_dir(env: Mapping[str, str]) -> Path:
    """`$XDG_STATE_HOME/maha`, by default under `~/.local/state`: the
    application log (spec hito 7, §1.11)."""
    xdg = env.get("XDG_STATE_HOME", "")
    # The XDG spec says to ignore relative paths.
    base = Path(xdg) if Path(xdg).is_absolute() else _home() / ".local" / "state"
    return base / "maha"


def load(*, cwd: Path, env: Mapping[str, str]) -> Settings:
    """Read, validate and combine the configuration; raise `ConfigError`."""
    user_path = user_config_path(env)
    project_path = cwd / PROJECT_FILE

    user = _validate(_UserFile, _read(user_path), user_path)
    project_data = _read(project_path)
    if "providers" in project_data:
        raise ConfigError(
            f"{project_path}: a project cannot declare [providers]. Providers "
            f"(URL and key variable) go only in {user_path}, so that a "
            "repository cannot send your key to another server."
        )
    project = _validate(_ProjectFile, project_data, project_path)

    providers = {**BUILTIN_PROVIDERS, **user.providers}
    provider_name = project.provider or user.provider or DEFAULT_PROVIDER
    if provider_name not in providers:
        raise ConfigError(
            f"unknown provider {provider_name!r}. "
            f"Available: {', '.join(sorted(providers))}."
        )
    model = project.model or user.model
    if model is None:
        # No default model in the code: model ids change too often.
        raise ConfigError(
            f"no model configured. Add it to {user_path}, for example:\n\n"
            f'  provider = "{provider_name}"\n'
            '  model = "<model id from your provider>"'
        )

    provider = providers[provider_name]
    return Settings(
        provider_name=provider_name,
        provider=provider,
        model=model,
        limits=_stricter(user.limits, project.limits),
        api_key=_api_key(provider_name, provider, env),
    )


def _stricter(user: _Limits, project: _Limits) -> TurnLimits:
    """Of each limit, the lower of the two files: a project can tighten the
    user's limits, never loosen them."""
    values: dict[str, Any] = {}
    for name in _Limits.model_fields:
        set_to = [
            v for v in (getattr(user, name), getattr(project, name)) if v is not None
        ]
        if set_to:
            values[name] = min(set_to)
    return TurnLimits(**values)


def _home() -> Path:
    """The user's home; without one (no HOME, no entry in passwd), a
    `ConfigError` that says what to do, not a traceback."""
    try:
        return Path.home()
    except RuntimeError:
        raise ConfigError(
            "cannot find your home folder: set HOME, or XDG_CONFIG_HOME, "
            "XDG_DATA_HOME and XDG_STATE_HOME"
        ) from None


def _read(path: Path) -> dict[str, Any]:
    """The TOML table in `path`, or an empty one if the file does not exist."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror}") from None
    except UnicodeDecodeError:
        raise ConfigError(f"{path} is not valid UTF-8") from None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from None


def _validate[T: BaseModel](model: type[T], data: dict[str, Any], path: Path) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "\n".join(
            f"  {'.'.join(str(part) for part in error['loc'])}: "
            + ("unknown field" if error["type"] == "extra_forbidden" else error["msg"])
            for error in exc.errors()
        )
        raise ConfigError(f"invalid configuration in {path}:\n{problems}") from None


def _api_key(
    name: str, provider: ProviderSettings, env: Mapping[str, str]
) -> str | None:
    """The key, from the environment. `maha` never reads a `.env` file."""
    if provider.api_key_env is None:
        return None
    key = env.get(provider.api_key_env, "").strip()
    if not key:
        raise ConfigError(
            f"{provider.api_key_env} is not set: it holds the key for provider "
            f"{name!r}. In development: uv run --env-file .env maha"
        )
    return key
