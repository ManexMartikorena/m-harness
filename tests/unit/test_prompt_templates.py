"""The prompt templates of the package (spec hito 10, §1.3, and §4, test 1):
each one fills with the values the code gives it, and the tool guidance
speaks of real tools."""

from importlib import resources
from pathlib import Path

from mharness.bootstrap import _tools
from mharness.domain.prompt import render, sections, tool_guidance

PROMPTS = resources.files("mharness") / "prompts"
TOOLS = _tools(Path.cwd(), {}).names()


def read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def test_the_base_fills_with_the_tools() -> None:
    text = render(
        read("base.md"), {"tools": tool_guidance(sections(read("tools.md")), TOOLS)}
    )

    assert "{{" not in text
    assert "- read_file: " in text
    assert "- run_command: " in text


def test_every_tool_has_guidance_and_every_guidance_a_tool() -> None:
    assert sorted(sections(read("tools.md"))) == sorted(TOOLS)


def test_the_base_is_short() -> None:
    # Under 1,500 tokens (§1.3); 4 characters a token is a safe upper bound
    # for English text.
    text = render(
        read("base.md"), {"tools": tool_guidance(sections(read("tools.md")), TOOLS)}
    )

    assert len(text) < 1_500 * 4
