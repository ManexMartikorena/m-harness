"""The fixed part of every call, bounded (spec hito 11, §1.1, rule 1, and
§4, test 3): maha's base system prompt and its tools go in every call of
every session, so they are paid in every step. If a change passes the
bound, this fails and the maintainer decides."""

from importlib import resources
from pathlib import Path

from mharness.bootstrap import _tools
from mharness.domain.context import estimate, estimate_tools
from mharness.domain.prompt import render, sections, tool_guidance
from tests.fakes.questions import FakePerson

# Tokens, estimated. Measured on 2026-11-17: base 706, tools 1,829.
FIXED_PART_MAX = 3_500

PROMPTS = resources.files("mharness") / "prompts"


def read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def test_the_base_prompt_and_the_tools_stay_under_the_bound() -> None:
    # Every tool, `ask_user` too: the prompt of a conversation has it.
    tools = _tools(Path.cwd(), {}, FakePerson())
    guidance = tool_guidance(sections(read("tools.md")), tools.names())
    base = render(read("base.md"), {"tools": guidance})

    fixed = estimate(base) + estimate_tools(tools.specs())

    assert fixed <= FIXED_PART_MAX, (
        f"the fixed part has {fixed:,} tokens, over {FIXED_PART_MAX:,}: "
        "every call of every session pays them (spec hito 11, §1.1)"
    )
