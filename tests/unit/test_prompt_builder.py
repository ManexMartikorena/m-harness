"""`SystemPromptBuilder`: the layers of a session's system prompt (spec hito
10, §1.1 to §1.3)."""

from mharness.application.prompt import PromptTemplates, SystemPromptBuilder
from mharness.domain.catalog import ModelInfo
from mharness.domain.prompt import INSTRUCTIONS_MAX, Layer
from mharness.ports.project import ProjectInfo
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.project import MemoryProject

TEMPLATES = PromptTemplates(
    base="You are maha.\n{{tools}}",
    tools={"read_file": "Read first.", "run_command": "Run tests."},
    families={"glm": "GLM: be brief."},
)
CATALOG = MemoryCatalog(
    [
        ModelInfo(provider="go", model="glm-5.3-flash", family="glm"),
        ModelInfo(provider="go", model="kimi-k2.7-code", family="kimi"),
        ModelInfo(provider="go", model="plain"),
    ]
)


def builder(
    project: ProjectInfo | None = None,
    *,
    tools: tuple[str, ...] = ("read_file", "glob"),
    base: Layer | None = None,
    append: tuple[Layer, ...] = (),
) -> SystemPromptBuilder:
    return SystemPromptBuilder(
        project or MemoryProject(),
        TEMPLATES,
        catalog=CATALOG,
        provider="go",
        tools=tools,
        base=base,
        append=append,
    )


def kinds(text_layers: tuple[Layer, ...]) -> list[str]:
    return [layer.kind for layer in text_layers]


async def test_the_layers_in_their_order() -> None:
    project = MemoryProject(
        [
            Layer(kind="user", source="~/.config/maha/AGENTS.md", text="mine"),
            Layer(kind="project", source="AGENTS.md", text="theirs"),
        ]
    )
    append = (Layer(kind="append", source="--append-system-prompt", text="last"),)

    prompt = await builder(project, append=append).build("glm-5.3-flash")

    assert kinds(prompt.layers) == [
        "base",
        "family",
        "user",
        "project",
        "environment",
        "append",
    ]
    assert prompt.text.startswith("You are maha.\n- read_file: Read first.\n\n")
    assert "Run tests." not in prompt.text
    assert "GLM: be brief." in prompt.text
    assert prompt.text.endswith("last")


async def test_a_model_without_family_layer_has_none() -> None:
    for model in ("kimi-k2.7-code", "plain", "not-in-the-catalog"):
        prompt = await builder().build(model)
        assert "family" not in kinds(prompt.layers)


async def test_the_users_base_replaces_the_base_and_the_family() -> None:
    mine = Layer(kind="base", source="~/mi-base.md", text="My own base.")

    prompt = await builder(base=mine).build("glm-5.3-flash")

    assert kinds(prompt.layers) == ["base", "environment"]
    assert prompt.text.startswith("My own base.")


async def test_the_instructions_are_capped_with_a_warning() -> None:
    project = MemoryProject(
        [Layer(kind="project", source="AGENTS.md", text="a" * (INSTRUCTIONS_MAX + 5))],
        warnings=["CLAUDE.md: not UTF-8, not read"],
    )

    prompt = await builder(project).build("plain")

    assert "[truncated: 5 bytes more]" in prompt.text
    assert prompt.warnings[0] == "CLAUDE.md: not UTF-8, not read"
    assert prompt.warnings[1].startswith("AGENTS.md: cut")


async def test_a_resumed_session_says_where_it_started() -> None:
    prompt = await builder().build("plain", started_in="/home/ana/web")

    assert "This conversation started in /home/ana/web" in prompt.text


async def test_another_model_changes_only_the_family_layer() -> None:
    project = MemoryProject([Layer(kind="project", source="AGENTS.md", text="v1")])
    build = builder(project)
    prompt = await build.build("glm-5.3-flash")
    # An edit after the start counts only from the next session (§1.2).
    project.layers = [Layer(kind="project", source="AGENTS.md", text="v2")]

    other = build.for_model(prompt, "kimi-k2.7-code")
    back = build.for_model(other, "glm-5.3-flash")

    assert "family" not in kinds(other.layers)
    assert "v1" in other.text
    assert project.reads == 1
    assert back.text == prompt.text
