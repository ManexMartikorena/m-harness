"""The system prompt, built from layers (spec hito 10, §1.1 to §1.7).

The most stable layer goes first: a provider's prompt cache compares the
start of the request, byte by byte, so what changes least is written
first. The prompt is built once per session and never changes until the
next (§1.2). Pure: the files and the environment come from outside.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel

from mharness.domain.paths import printable

# What every instruction file together may bring (§1.4): this repo's
# AGENTS.md has 15.6 KB; Codex allows 32 KiB by default.
INSTRUCTIONS_MAX = 64 * 1024

# Where each layer goes, in this order (§1.1). Skills and memory, from
# hitos 13 and 14, go after "extra".
type LayerKind = Literal[
    "base", "family", "user", "project", "extra", "environment", "append"
]
ORDER: tuple[LayerKind, ...] = (
    "base",
    "family",
    "user",
    "project",
    "extra",
    "environment",
    "append",
)
# The layers that are instruction files, delimited with their source.
INSTRUCTION_KINDS: frozenset[LayerKind] = frozenset({"user", "project", "extra"})

_HOLE = re.compile(r"\{\{([a-z_]+)\}\}")
# A file cannot close its own block: the tag is written escaped.
_CLOSING = re.compile(r"</instructions\s*>", re.IGNORECASE)


class TemplateError(ValueError):
    """A template and its values do not match."""


def render(template: str, values: Mapping[str, str]) -> str:
    """Fill every `{{name}}` of `template`. A hole without a value, or a
    value without a hole, is an error: a typo never reaches the model."""
    holes = set(_HOLE.findall(template))
    missing = sorted(holes - values.keys())
    unused = sorted(values.keys() - holes)
    if missing or unused:
        raise TemplateError(f"template holes: missing {missing}, unused {unused}")
    return _HOLE.sub(lambda match: values[match.group(1)], template)


class Layer(BaseModel, frozen=True):
    """One part of the system prompt."""

    kind: LayerKind
    # Where it comes from, as the user reads it: "AGENTS.md",
    # "~/.config/maha/AGENTS.md", "maha".
    source: str
    text: str


class Environment(BaseModel, frozen=True):
    """What the model is told of where it runs (§1.7). Nothing that changes
    during a session: no git status, no file tree, no model name."""

    cwd: str
    # The root of the git repository around `cwd`, if any.
    git_root: str | None
    platform: str
    shell: str | None
    today: date
    # The directory of a resumed session that started somewhere else.
    started_in: str | None = None


def environment_layer(env: Environment) -> Layer:
    """The environment, as the model reads it."""
    lines = [f"Working directory: {printable(env.cwd)}"]
    if env.git_root is None:
        lines.append("Git repository: no")
    else:
        lines.append(f"Git repository: yes (root: {printable(env.git_root)})")
    lines.append(f"Platform: {env.platform}")
    if env.shell:
        lines.append(f"Shell: {printable(env.shell)}")
    lines.append(f"Today's date: {env.today.isoformat()}")
    if env.started_in is not None and env.started_in != env.cwd:
        # A session resumed from another directory (spec hito 6, §1.8).
        lines.append(
            f"This conversation started in {printable(env.started_in)}; "
            f"you now work in {printable(env.cwd)}."
        )
    body = "\n".join(lines)
    return Layer(
        kind="environment", source="maha", text=f"<environment>\n{body}\n</environment>"
    )


def cap(
    layers: Sequence[Layer], limit: int = INSTRUCTIONS_MAX
) -> tuple[list[Layer], list[str]]:
    """The instruction layers within `limit` bytes of UTF-8 between them, in
    their order, and a warning for each one cut. A file past the limit
    keeps only the mark, so the model knows it was there (§1.4)."""
    kept: list[Layer] = []
    warnings: list[str] = []
    left = limit
    for layer in layers:
        data = layer.text.encode("utf-8")
        if layer.kind not in INSTRUCTION_KINDS or len(data) <= left:
            kept.append(layer)
            if layer.kind in INSTRUCTION_KINDS:
                left -= len(data)
            continue
        more = len(data) - left
        # A cut in the middle of a character drops it.
        head = data[:left].decode("utf-8", errors="ignore")
        mark = f"[truncated: {more} bytes more]"
        text = f"{head}\n{mark}" if head else mark
        kept.append(layer.model_copy(update={"text": text}))
        warnings.append(
            f"{layer.source}: cut, the instructions pass "
            f"{limit // 1024} KiB ({more} bytes more)"
        )
        left = 0
    return kept, warnings


def _shown(layer: Layer) -> str:
    if layer.kind not in INSTRUCTION_KINDS:
        return layer.text
    text = _CLOSING.sub("&lt;/instructions&gt;", layer.text)
    source = printable(layer.source).replace('"', "'")
    return f'<instructions source="{source}">\n{text}\n</instructions>'


class SystemPrompt(BaseModel, frozen=True):
    """The layers of one session's system prompt, in their order."""

    layers: tuple[Layer, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(_shown(layer) for layer in self.layers if layer.text)

    @property
    def fingerprint(self) -> str:
        """The whole prompt's, for the trace (§1.13)."""
        return fingerprint(self.text)

    @property
    def base_fingerprint(self) -> str:
        """The base and family layers', without instructions or
        environment: what a baseline of the evals depends on (§1.13)."""
        return fingerprint(
            "\n\n".join(
                layer.text for layer in self.layers if layer.kind in ("base", "family")
            )
        )


def compose(layers: Iterable[Layer]) -> SystemPrompt:
    """The layers in the order of §1.1; those of the same kind keep the
    order they come in (the project's go from the git root down)."""
    rank = {kind: index for index, kind in enumerate(ORDER)}
    return SystemPrompt(
        layers=tuple(sorted(layers, key=lambda layer: rank[layer.kind]))
    )


def fingerprint(text: str) -> str:
    """12 hex digits of the SHA-256 of `text`: short to read, and two
    different prompts do not share one in practice."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
