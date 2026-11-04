"""The system prompt of a session, from its layers (spec hito 10, §1.1 to
§1.8).

Built when a session's agent is made (start, /new, /resume) and fixed
until the next: a provider's prompt cache compares the start of every
request (§1.2). `/model` changes only the family layer: the cache of a
provider is per model, so another model loses it anyway.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from mharness.domain.prompt import (
    Layer,
    SystemPrompt,
    cap,
    compose,
    environment_layer,
    render,
    tool_guidance,
)
from mharness.ports.catalog import ModelCatalog
from mharness.ports.project import ProjectInfo

MAHA = "maha"


@dataclass(frozen=True)
class PromptTemplates:
    """The templates of the package, read by `bootstrap`: the base, one
    line of guidance per tool, and a layer per family of models."""

    base: str
    tools: Mapping[str, str]
    families: Mapping[str, str]


class SystemPromptBuilder:
    """Puts together the layers of a session's system prompt.

    `tools` are the names of the registered tools, in their order: the
    base speaks only of those. `base` is the user's own base
    (`system_prompt_file`, `--system-prompt-file`), which replaces the
    base and the family layer; `append` goes last
    (`--append-system-prompt`).
    """

    def __init__(
        self,
        project: ProjectInfo,
        templates: PromptTemplates,
        *,
        catalog: ModelCatalog,
        provider: str,
        tools: Sequence[str],
        base: Layer | None = None,
        append: Sequence[Layer] = (),
    ) -> None:
        self._project = project
        self._templates = templates
        self._catalog = catalog
        self._provider = provider
        self._tools = tuple(tools)
        self._base = base
        self._append = tuple(append)

    async def build(self, model: str, *, started_in: str | None = None) -> SystemPrompt:
        """The prompt of a new or resumed session with `model`; `started_in`
        is the directory of a resumed session (spec hito 6, §1.8)."""
        instructions = await self._project.instructions()
        environment = await self._project.environment()
        if started_in is not None:
            environment = environment.model_copy(update={"started_in": started_in})
        kept, cut = cap(instructions.layers)
        family = self._family(model)
        layers = [
            self._base or self._default_base(),
            *([family] if family is not None else []),
            *kept,
            environment_layer(environment),
            *self._append,
        ]
        prompt = compose(layers)
        return prompt.model_copy(update={"warnings": (*instructions.warnings, *cut)})

    def for_model(self, prompt: SystemPrompt, model: str) -> SystemPrompt:
        """`prompt` with the family layer of `model`: the rest stays."""
        rest = [layer for layer in prompt.layers if layer.kind != "family"]
        family = self._family(model)
        changed = compose([*rest, *([family] if family is not None else [])])
        return changed.model_copy(update={"warnings": prompt.warnings})

    def base_fingerprint(self, model: str) -> str:
        """The fingerprint of the base and family layers with `model`: what
        a baseline of the evals depends on (§1.13)."""
        family = self._family(model)
        layers = [self._base or self._default_base(), *([family] if family else [])]
        return compose(layers).base_fingerprint

    def _default_base(self) -> Layer:
        guidance = tool_guidance(self._templates.tools, self._tools)
        return Layer(
            kind="base",
            source=MAHA,
            text=render(self._templates.base, {"tools": guidance}),
        )

    def _family(self, model: str) -> Layer | None:
        """The layer of the model's family, if it has one and the base is
        maha's: a base of the user's own goes alone (§1.3)."""
        if self._base is not None:
            return None
        info = self._catalog.get(self._provider, model)
        if info is None or info.family is None:
            return None
        text = self._templates.families.get(info.family)
        if not text:
            return None
        return Layer(kind="family", source=f"{MAHA} ({info.family})", text=text)
