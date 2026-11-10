"""`/init` (spec hito 10, §1.9, and §4, test 13)."""

import io
from pathlib import Path

from mharness.adapters.cli.conversation import converse
from mharness.adapters.cli.init import TAKES_EFFECT, Init
from mharness.application.agent import Agent
from mharness.application.tools import ToolRegistry
from mharness.bootstrap import _init
from mharness.domain.messages import ToolCallBlock
from mharness.domain.prompt import render
from mharness.domain.tools import Permission
from tests.adapters.test_conversation import KNOWN, solo
from tests.fakes.approval import FakeApproval
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import FakeModelClient, reply, tool_calls
from tests.fakes.terminal import ScriptedInput
from tests.fakes.tools import EchoParams

TEMPLATE = "Write AGENTS.md at {{root}}.{{extra}}"


def test_the_message_names_the_root_and_what_to_stress(tmp_path: Path) -> None:
    init = Init(template=TEMPLATE, root=tmp_path)

    assert init.text(None) == f"Write AGENTS.md at {tmp_path}."
    assert init.text("los tests van con uv") == (
        f"Write AGENTS.md at {tmp_path}.\n\nThe user wants this stressed:\n"
        "<user_notes>\nlos tests van con uv\n</user_notes>"
    )


def test_the_package_template_fills(tmp_path: Path) -> None:
    init = _init(tmp_path)

    text = init.text("algo")

    assert "{{" not in text
    assert str(tmp_path) in text
    assert "improve it in place" in text
    assert "CLAUDE.md, start from it" in text


def test_agents_md_goes_to_the_git_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    inner = repo / "src" / "app"
    inner.mkdir(parents=True)
    loose = tmp_path / "suelto"
    loose.mkdir()

    assert _init(inner).target == repo / "AGENTS.md"
    # Without git, where maha runs.
    assert _init(loose).target == loose / "AGENTS.md"


class WritesAgents:
    """A tool that writes AGENTS.md, as the agent would after asking."""

    name = "echo"
    description = "Write AGENTS.md."
    params = EchoParams
    permission: Permission = "read"
    waits_for_user = False

    def __init__(self, path: Path) -> None:
        self._path = path

    async def approval(self, params: EchoParams) -> None:
        return None

    async def run(self, params: EchoParams) -> str:
        self._path.write_text(params.text, encoding="utf-8")
        return "written"

    def summary(self, result: str) -> str:
        return result


async def init_run(tmp_path: Path, fake: FakeModelClient, line: str) -> str:
    out = io.StringIO()
    agent = Agent(
        fake,
        ToolRegistry([WritesAgents(tmp_path / "AGENTS.md")]),
        gate=FakeApproval(),
        model="m",
        catalog=MemoryCatalog(),
        provider="opencode-go",
    )
    await converse(
        solo(agent),
        provider="p",
        catalog=KNOWN,
        read_line=ScriptedInput(line, "/exit"),
        out=out,
        err=io.StringIO(),
        init=Init(template=TEMPLATE, root=tmp_path),
    )
    return out.getvalue()


async def test_init_is_a_turn_with_the_template(tmp_path: Path) -> None:
    write = ToolCallBlock(id="c1", name="echo", arguments='{"text": "# Agents"}')
    fake = FakeModelClient([tool_calls(write), reply("Escrito.")])

    out = await init_run(tmp_path, fake, "/init usa uv")

    [user] = fake.requests[0].messages
    assert user.text == render(
        TEMPLATE,
        {
            "root": str(tmp_path),
            "extra": "\n\nThe user wants this stressed:\n<user_notes>\nusa uv"
            "\n</user_notes>",
        },
    )
    assert (tmp_path / "AGENTS.md").read_text() == "# Agents"
    assert f"Escrito.\n  {TAKES_EFFECT}\n" in out


async def test_nothing_written_says_nothing(tmp_path: Path) -> None:
    fake = FakeModelClient([reply("No hace falta.")])

    out = await init_run(tmp_path, fake, "/init")

    assert TAKES_EFFECT not in out


async def test_an_agents_md_that_was_already_there_and_changed_is_told(
    tmp_path: Path,
) -> None:
    (tmp_path / "AGENTS.md").write_text("# Viejo", encoding="utf-8")
    write = ToolCallBlock(id="c1", name="echo", arguments='{"text": "# Nuevo, mejor"}')
    fake = FakeModelClient([tool_calls(write), reply("Mejorado.")])

    out = await init_run(tmp_path, fake, "/init")

    assert TAKES_EFFECT in out
