"""The instruction files of the folders the model works in, after a tool's
result (spec hito 11, §1.14, and §4, test 16)."""

from mharness.application.agent import Agent
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import AgentEvent, ToolFinished
from mharness.domain.limits import TurnLimits
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.prompt import (
    INSTRUCTIONS_MAX,
    Instructions,
    Layer,
    attached_instructions,
)
from mharness.domain.tools import ToolError
from tests.fakes.approval import FakeApproval
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import FakeModelClient, reply, tool_calls
from tests.fakes.project import MemoryProject
from tests.fakes.retry import NO_RETRIES
from tests.fakes.tools import FakeTool

FILE = "/home/ana/tienda/api/app.py"
API = Layer(kind="project", source="api/AGENTS.md", text="Tests: make test.")
BLOCK = '<instructions source="api/AGENTS.md">\nTests: make test.\n</instructions>'


def call(id: str) -> ToolCallBlock:
    return ToolCallBlock(id=id, name="echo", arguments='{"text": "x"}')


def agent(
    fake: FakeModelClient,
    project: MemoryProject,
    tool: FakeTool | None = None,
    history: list[Message] | None = None,
) -> Agent:
    return Agent(
        fake,
        ToolRegistry([tool or FakeTool(touches=FILE)]),
        gate=FakeApproval(),
        model="glm-5.3-flash",
        catalog=MemoryCatalog(),
        provider="opencode-go",
        limits=TurnLimits(max_steps=10),
        history=history or [],
        retry=NO_RETRIES,
        project=project,
    )


def api_project(*layers: Layer, warnings: tuple[str, ...] = ()) -> MemoryProject:
    found = Instructions(layers=layers or (API,), warnings=warnings)
    return MemoryProject(nested={FILE: found})


async def run(subject: Agent, text: str = "Lee app.py") -> list[AgentEvent]:
    return [event async for event in subject.run(text)]


def results(subject: Agent) -> list[str]:
    return [
        block.content
        for message in subject.messages
        for block in message.blocks
        if isinstance(block, ToolResultBlock)
    ]


async def test_the_files_of_the_folder_come_after_the_result() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho.")])
    project = api_project()
    subject = agent(fake, project)

    await run(subject)

    assert results(subject) == [f"echo: x\n\n{BLOCK}"]
    assert project.asked == [FILE]
    assert attached_instructions(results(subject)[0]) == [("api/AGENTS.md", BLOCK)]


async def test_each_file_comes_once() -> None:
    fake = FakeModelClient(
        [
            tool_calls(call("c1"), call("c2")),
            tool_calls(call("c3")),
            reply("Hecho."),
            tool_calls(call("c4")),
            reply("Hecho."),
        ]
    )
    subject = agent(fake, api_project())

    await run(subject)
    await run(subject, "Otra vez")

    assert results(subject) == [
        f"echo: x\n\n{BLOCK}",
        "echo: x",
        "echo: x",
        "echo: x",
    ]


async def test_not_those_of_the_system_prompt() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho.")])
    subject = agent(fake, api_project())
    # A glob of `instructions` already put it in the system prompt.
    subject.instructions = (API.model_copy(update={"kind": "extra"}),)

    await run(subject)

    assert results(subject) == ["echo: x"]


async def test_after_archiving_they_come_again() -> None:
    history = [
        Message(role="user", blocks=[TextBlock(text="Lee app.py")]),
        Message(role="assistant", blocks=[call("h1")]),
        Message(
            role="tool",
            blocks=[ToolResultBlock(call_id="h1", content=f"echo: x\n\n{BLOCK}")],
        ),
        Message(role="assistant", blocks=[TextBlock(text="Leído.")]),
    ]
    index = Message(role="user", blocks=[TextBlock(text="<context-archive>…")])
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho.")])
    subject = agent(fake, api_project(), history=history)
    subject.restore(len(history), index, None)

    await run(subject)

    assert results(subject)[-1] == f"echo: x\n\n{BLOCK}"


async def test_without_archiving_a_resumed_session_has_them() -> None:
    history = [
        Message(role="user", blocks=[TextBlock(text="Lee app.py")]),
        Message(role="assistant", blocks=[call("h1")]),
        Message(
            role="tool",
            blocks=[ToolResultBlock(call_id="h1", content=f"echo: x\n\n{BLOCK}")],
        ),
        Message(role="assistant", blocks=[TextBlock(text="Leído.")]),
    ]
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho.")])
    subject = agent(fake, api_project(), history=history)

    await run(subject)

    assert results(subject)[-1] == "echo: x"


async def test_all_of_them_within_the_limit_of_the_system_prompts() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho.")])
    subject = agent(fake, api_project())
    almost = INSTRUCTIONS_MAX - 5
    subject.instructions = (
        Layer(kind="project", source="AGENTS.md", text="a" * almost),
    )

    events = await run(subject)

    [result] = results(subject)
    assert result.endswith(
        '<instructions source="api/AGENTS.md">\n'
        "Tests\n[truncated: 12 bytes more]\n</instructions>"
    )
    [finished] = [e for e in events if isinstance(e, ToolFinished)]
    assert finished.warnings == (
        "api/AGENTS.md: cut, the instructions pass 64 KiB (12 bytes more)",
    )


async def test_what_cannot_be_read_is_told_once() -> None:
    fake = FakeModelClient(
        [tool_calls(call("c1")), tool_calls(call("c2")), reply("Hecho.")]
    )
    project = MemoryProject(
        nested={
            FILE: Instructions(warnings=("api/AGENTS.md: a secret file, not read",))
        }
    )
    subject = agent(fake, project)

    events = await run(subject)

    told = [e.warnings for e in events if isinstance(e, ToolFinished)]
    assert told == [("api/AGENTS.md: a secret file, not read",), ()]
    assert results(subject) == ["echo: x", "echo: x"]


async def test_an_error_result_gets_none() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho.")])
    project = api_project()
    tool = FakeTool(touches=FILE, results=[ToolError("not found: app.py")])
    subject = agent(fake, project, tool)

    await run(subject)

    assert results(subject) == ["error: not found: app.py"]
    assert project.asked == []


async def test_a_tool_that_touches_nothing_asks_nothing() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho.")])
    project = api_project()
    subject = agent(fake, project, FakeTool())

    await run(subject)

    assert results(subject) == ["echo: x"]
    assert project.asked == []
