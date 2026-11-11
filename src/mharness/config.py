"""Load and validate the configuration (spec hito 2, §1.10).

Three levels, the later one winning for `provider`, `model`,
`fallback_model`, `effort` and `cache_ttl`; of each limit of the turn, the
stricter one wins (spec hito 8, §3.2):

1. built-in providers, in this module;
2. the user's file, `$XDG_CONFIG_HOME/maha/config.toml`;
3. the project's file, `.maha/config.toml` in the working directory.

Providers (URL and key variable) can only be declared by the user: a project
file is untrusted input, and could send the user's key to another server.

Start-up plumbing: only `mharness.bootstrap` uses it, once, before the core.
"""

import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePath
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    ValidationError,
    model_validator,
)

from mharness.domain.catalog import SpokenApi
from mharness.domain.environment import is_credential
from mharness.domain.limits import TurnLimits
from mharness.domain.model import CacheTtl, Effort
from mharness.domain.money import Usd
from mharness.domain.paths import is_secret

PROJECT_FILE = Path(".maha") / "config.toml"
DEFAULT_PROVIDER = "opencode-go"


# How long Anthropic's prompt cache lasts.


class ConfigError(Exception):
    """The configuration is missing or wrong; the message says what to do."""


class ProviderSettings(BaseModel, frozen=True, extra="forbid"):
    """How to reach one provider."""

    # The format of its models, unless the catalog says another (spec hito
    # 9, §1.1); `base_url` is where it is spoken.
    api: SpokenApi = "openai-chat"
    base_url: str = Field(min_length=1)
    # Where it speaks its other formats, if it serves several.
    endpoints: dict[SpokenApi, Annotated[str, Field(min_length=1)]] = {}
    # Name of the environment variable that holds the key; None sends no key.
    api_key_env: str | None = None
    session_header: str | None = None
    # The version of Anthropic's API it is asked for; None: the adapter's,
    # the latest (spec hito 9, decision 2). Written once, there (audit after
    # hito 10, M5).
    anthropic_version: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _endpoints_are_other_formats(self) -> ProviderSettings:
        # Its own format is spoken at `base_url`: an endpoint for it would
        # be ignored without a word (deep audit after hito 9, M10).
        if self.api in self.endpoints:
            raise ValueError(
                f"endpoints.{self.api} is this provider's own format: use base_url"
            )
        return self

    def url(self, api: str) -> str | None:
        """Where this provider speaks `api`; None if it does not."""
        if api == self.api:
            return self.base_url
        return next((url for name, url in self.endpoints.items() if name == api), None)


BUILTIN_PROVIDERS: Mapping[str, ProviderSettings] = {
    "opencode-go": ProviderSettings(
        base_url="https://opencode.ai/inference/go/openai/v1",
        endpoints={"anthropic": "https://opencode.ai/inference/go/anthropic/v1"},
        api_key_env="OPENCODE_API_KEY",
        session_header="x-opencode-session",
    ),
    # The API, direct: a key of the Claude Console (spec hito 9, §1.1).
    "anthropic": ProviderSettings(
        api="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
    ),
    "opencode-zen": ProviderSettings(
        base_url="https://opencode.ai/inference/openai/v1",
        endpoints={"anthropic": "https://opencode.ai/inference/anthropic/v1"},
        api_key_env="OPENCODE_API_KEY",
        session_header="x-opencode-session",
    ),
}


class Settings(BaseModel, frozen=True):
    """Everything `maha` needs to start a conversation."""

    provider_name: str
    provider: ProviderSettings
    # None only for the commands that never call the model (`load()`).
    model: str | None
    # Answers when the retries of `model` run out (spec hito 8, §1.14).
    fallback_model: str | None = None
    # Writes the titles of the sessions; None: the catalog's for the
    # provider, or the session's (spec hito 10, §1.12).
    small_model: str | None = None
    # None: the model's own (spec hito 9, §1.7).
    effort: Effort | None = None
    # How long Anthropic's prompt cache lasts (spec hito 9, decision 9).
    cache_ttl: CacheTtl = "5m"
    limits: TurnLimits = TurnLimits()
    # Kept out of repr, so it never lands in a log or a traceback.
    api_key: str | None = Field(default=None, repr=False)
    # What the project's file chose, by name: maha says it at start, so a
    # foreign repository cannot raise the cost unseen (deep audit after
    # hito 9, M4, a decision of the maintainer).
    from_project: dict[str, str] = {}
    # Extra instruction files of the system prompt, paths or globs from the
    # working directory: the user's, and the project's, which never leave
    # the project (spec hito 10, §1.5).
    instructions: tuple[str, ...] = ()
    project_instructions: tuple[str, ...] = ()
    # Read CLAUDE.md where there is no AGENTS.md (spec hito 10, §1.4).
    compat_claude: bool = True
    # The user's own base of the system prompt, instead of maha's; only
    # from the user's file (spec hito 10, §1.3).
    system_prompt_file: Path | None = None
    # More variables the shell commands get, as a proxy or `JAVA_HOME`;
    # only from the user's file, never a credential (audit after hito 10,
    # P5).
    command_env: tuple[str, ...] = ()


class _Limits(BaseModel, extra="forbid"):
    """`[limits]`: each one, if the file sets it."""

    # Strict: `true` is not 1 step nor 1 second; the cost within the bounds
    # of an amount in USD, or the turn could not check it (review of the
    # deep audit).
    max_steps: StrictInt | None = Field(default=None, ge=1)
    max_cost: Usd | None = None
    max_tokens: StrictInt | None = Field(default=None, ge=1)
    timeout: StrictFloat | None = Field(default=None, gt=0)


class _ProjectFile(BaseModel, extra="forbid"):
    provider: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    fallback_model: str | None = Field(default=None, min_length=1)
    small_model: str | None = Field(default=None, min_length=1)
    effort: Effort | None = None
    cache_ttl: CacheTtl | None = None
    limits: _Limits = _Limits()
    instructions: list[Annotated[str, Field(min_length=1)]] = []
    compat_claude: StrictBool | None = None


class _UserFile(_ProjectFile):
    providers: dict[str, ProviderSettings] = {}
    system_prompt_file: str | None = Field(default=None, min_length=1)
    command_env: list[Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]] = []


def user_config_path(env: Mapping[str, str]) -> Path:
    """`$XDG_CONFIG_HOME/maha/config.toml`, by default under `~/.config`."""
    return _config_dir(env) / "config.toml"


def user_catalog_path(env: Mapping[str, str]) -> Path:
    """`$XDG_CONFIG_HOME/maha/models.toml`: the user's prices, which win over
    the built-in ones (spec hito 7, §1.3). Never a project's."""
    return _config_dir(env) / "models.toml"


def config_dir(env: Mapping[str, str]) -> Path:
    """`$XDG_CONFIG_HOME/maha`: the user's files of maha, also their
    `AGENTS.md` (spec hito 10, §1.4)."""
    return _config_dir(env)


def home() -> Path:
    """The user's home, or a `ConfigError` that says what to do."""
    return _home()


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


def load(*, cwd: Path, env: Mapping[str, str], calls_model: bool = True) -> Settings:
    """Read, validate and combine the configuration; raise `ConfigError`.
    Without `calls_model`, a missing model or key is no error: the commands
    that never call the model do not need them (`maha sessions`, `stats`…),
    and `model` may be None."""
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
    if "system_prompt_file" in project_data:
        raise ConfigError(
            f"{project_path}: a project cannot replace the base of the system "
            f"prompt (system_prompt_file); it goes only in {user_path}. A "
            "project adds its instructions in AGENTS.md."
        )
    if "command_env" in project_data:
        raise ConfigError(
            f"{project_path}: a project cannot choose command_env: what the "
            f"commands see of your environment goes only in {user_path}."
        )
    project = _validate(_ProjectFile, project_data, project_path)
    for pattern in project.instructions:
        _inside_project(pattern, project_path)

    providers = {**BUILTIN_PROVIDERS, **user.providers}
    provider_name = project.provider or user.provider or DEFAULT_PROVIDER
    if provider_name not in providers:
        raise ConfigError(
            f"unknown provider {provider_name!r}. "
            f"Available: {', '.join(sorted(providers))}."
        )
    model = project.model or user.model
    if model is None and calls_model:
        # No default model in the code: model ids change too often.
        raise ConfigError(
            f"no model configured. Add it to {user_path}, for example:\n\n"
            f'  provider = "{provider_name}"\n'
            '  model = "<model id from your provider>"'
        )

    provider = providers[provider_name]
    keys = {each.api_key_env for each in providers.values() if each.api_key_env}
    for name in user.command_env:
        if is_credential(name) or name in keys:
            raise ConfigError(
                f"{user_path}: command_env {name!r} looks like a credential: "
                "the commands, and from their output the model, would see it."
            )
    return Settings(
        provider_name=provider_name,
        provider=provider,
        model=model,
        fallback_model=project.fallback_model or user.fallback_model,
        small_model=project.small_model or user.small_model,
        effort=project.effort or user.effort,
        cache_ttl=project.cache_ttl or user.cache_ttl or "5m",
        limits=_stricter(user.limits, project.limits),
        instructions=tuple(user.instructions),
        project_instructions=tuple(dict.fromkeys(project.instructions)),
        compat_claude=_first(project.compat_claude, user.compat_claude, True),
        system_prompt_file=(
            None
            if user.system_prompt_file is None
            else Path(user.system_prompt_file).expanduser()
        ),
        command_env=tuple(dict.fromkeys(user.command_env)),
        api_key=_api_key(provider_name, provider, env, need=calls_model),
        from_project={
            name: value
            for name in (
                "provider",
                "model",
                "fallback_model",
                "small_model",
                "effort",
                "cache_ttl",
            )
            if (value := getattr(project, name)) is not None
        },
    )


def _inside_project(pattern: str, path: Path) -> None:
    """A project's instruction file stays in the project, and is never a
    secret: a cloned repository could send the user's key to the provider
    (spec hito 10, §1.5). The files a glob finds are checked again when
    they are read."""
    parts = PurePath(pattern).parts
    if pattern.startswith("~") or PurePath(pattern).is_absolute() or ".." in parts:
        raise ConfigError(
            f"{path}: instructions {pattern!r} must be a path inside the project"
        )
    if is_secret(PurePath(pattern)):
        raise ConfigError(
            f"{path}: instructions {pattern!r} is a secret file: its content "
            "would go to the model provider"
        )


def _first(*values: bool | None) -> bool:
    """The first value that is set."""
    return next(value for value in values if value is not None)


def _stricter(user: _Limits, project: _Limits) -> TurnLimits:
    """Of each limit, the lower of the two files: a project can tighten the
    user's limits, never loosen them. What the user does not set is the
    default, also for the project: 25 steps stay 25 (audit of hito 8)."""
    defaults = TurnLimits()
    values: dict[str, Any] = {}
    for name in _Limits.model_fields:
        mine = getattr(user, name)
        if mine is None:
            mine = getattr(defaults, name)
        theirs = getattr(project, name)
        set_to = [value for value in (mine, theirs) if value is not None]
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
    name: str, provider: ProviderSettings, env: Mapping[str, str], *, need: bool
) -> str | None:
    """The key, from the environment. `maha` never reads a `.env` file."""
    if provider.api_key_env is None:
        return None
    key = env.get(provider.api_key_env, "").strip()
    valid = key.isascii() and key.isprintable() and " " not in key
    if not need and not (key and valid):
        # A command that does not call the model must not fail over a key
        # it does not use (review of the deep audit).
        return None
    if not key:
        raise ConfigError(
            f"{provider.api_key_env} is not set: it holds the key for provider "
            f"{name!r}. In development: uv run --env-file .env maha"
        )
    if not valid:
        # It goes in an HTTP header; never echoed (deep audit after hito 9).
        raise ConfigError(
            f"{provider.api_key_env} has characters a key cannot have (spaces, "
            "accents or control characters): copy it again from the console"
        )
    return key
