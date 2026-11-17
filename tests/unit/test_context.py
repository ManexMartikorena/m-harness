import pytest
from pydantic import ValidationError

from mharness.domain.context import (
    DEFAULT_BUDGET,
    OUTPUT_LIMIT,
    ContextPolicy,
    estimate,
    estimate_messages,
    estimate_tools,
    fit,
    message_text,
)
from mharness.domain.messages import (
    Message,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from mharness.domain.model import ToolSpec

# estimate (spec hito 11, §1.2)


def test_estimate_of_nothing_is_zero() -> None:
    assert estimate("") == 0


def test_estimate_rounds_up() -> None:
    assert estimate("abcd") == 1
    assert estimate("abcde") == 2


def test_estimate_counts_characters_not_bytes() -> None:
    # "ñ" is two bytes in UTF-8, one character.
    assert estimate("ñañañaña") == 2


def test_message_text_has_what_the_model_reads() -> None:
    message = Message(
        role="assistant",
        blocks=[
            ReasoningBlock(text="pienso"),
            TextBlock(text="hola"),
            ToolCallBlock(id="c1", name="read_file", arguments='{"path": "a"}'),
        ],
    )

    text = message_text(message)

    assert "pienso" in text
    assert "hola" in text
    assert "read_file" in text
    assert '{"path": "a"}' in text


def test_estimate_messages_adds_every_message() -> None:
    messages = [
        Message(role="user", blocks=[TextBlock(text="a" * 40)]),
        Message(
            role="tool",
            blocks=[ToolResultBlock(call_id="c1", content="b" * 80)],
        ),
    ]

    assert estimate_messages(messages) == 10 + 20


def test_estimate_tools_includes_the_schema() -> None:
    small = ToolSpec(name="t", description="d", input_schema={})
    big = ToolSpec(
        name="t",
        description="d",
        input_schema={"properties": {"path": {"type": "string"}}},
    )

    assert estimate_tools([big]) > estimate_tools([small]) > 0


# ContextPolicy (§1.3)


def test_the_default_budget_is_100_000() -> None:
    assert ContextPolicy().budget == DEFAULT_BUDGET == 100_000


def test_a_big_window_is_capped_by_the_budget() -> None:
    policy = ContextPolicy(window=1_000_000)

    assert policy.reserve == 150_000
    assert policy.ceiling == 100_000


def test_a_small_window_keeps_its_reserve() -> None:
    # The example of §1.3: a window of 64,000 gives a ceiling of 48,000.
    policy = ContextPolicy(window=64_000)

    assert policy.reserve == 16_000
    assert policy.ceiling == 48_000


def test_the_reserve_is_15_percent_of_a_window_over_the_minimum() -> None:
    policy = ContextPolicy(budget=500_000, window=200_000)

    assert policy.reserve == 30_000
    assert policy.ceiling == 170_000


def test_an_unknown_window_is_the_budget() -> None:
    policy = ContextPolicy()

    assert policy.reserve == 16_000
    assert policy.ceiling == 84_000


def test_a_tiny_window_keeps_half_for_the_prompt() -> None:
    policy = ContextPolicy(window=8_192)

    assert policy.reserve == 4_096
    assert policy.ceiling == 4_096


def test_a_configured_budget_lowers_the_ceiling() -> None:
    assert ContextPolicy(budget=20_000, window=1_000_000).ceiling == 20_000


def test_the_tail_is_30_percent_of_the_ceiling() -> None:
    assert ContextPolicy(window=1_000_000).tail == 30_000


@pytest.mark.parametrize("field", ["budget", "window"])
def test_policy_rejects_zero(field: str) -> None:
    with pytest.raises(ValidationError):
        ContextPolicy.model_validate({field: 0})


# max_tokens per call (§1.4)


def test_answer_room_is_max_output_when_it_fits() -> None:
    policy = ContextPolicy(window=262_144)

    assert policy.answer_room(10_000, 131_072) == 131_072


def test_answer_room_never_passes_the_window() -> None:
    policy = ContextPolicy(window=262_144)

    assert policy.answer_room(200_000, 262_144) == 62_144


def test_answer_room_without_max_output_is_what_is_left() -> None:
    assert ContextPolicy(window=100_000).answer_room(30_000, None) == 70_000


def test_answer_room_with_an_unknown_window_is_max_output() -> None:
    assert ContextPolicy().answer_room(500_000, 8_192) == 8_192


def test_answer_room_when_the_prompt_fills_the_window_is_none() -> None:
    assert ContextPolicy(window=100_000).answer_room(100_000, 8_192) is None


def test_under_the_ceiling_there_is_always_the_reserve() -> None:
    policy = ContextPolicy(window=64_000)

    room = policy.answer_room(policy.ceiling, 1_000_000)

    assert room == policy.reserve


# fit (§1.6)


def test_fit_leaves_a_short_text_as_it_is() -> None:
    assert fit("hola\nmundo") == "hola\nmundo"


def test_fit_leaves_a_text_of_exactly_the_limit() -> None:
    text = "a" * OUTPUT_LIMIT

    assert fit(text) == text


def test_fit_keeps_the_beginning_and_the_end() -> None:
    lines = [f"line {i}" for i in range(20_000)]
    text = "\n".join(lines)

    out = fit(text)

    assert len(out) <= OUTPUT_LIMIT
    assert out.startswith("line 0\nline 1\n")
    assert out.endswith("line 19998\nline 19999")
    assert "[output cut:" in out


def test_fit_cuts_at_line_breaks() -> None:
    lines = [f"line {i}" for i in range(20_000)]

    out = fit("\n".join(lines)).split("\n")

    mark = next(i for i, line in enumerate(out) if line.startswith("… [output cut:"))
    assert out[mark - 1] in lines
    assert out[mark + 1] in lines


def test_fit_says_how_much_was_cut() -> None:
    text = "x" * 100_000

    head, mark, tail = fit(text).split("\n")

    cut = len(text) - len(head) - len(tail)
    assert mark == f"… [output cut: {cut:,} of 100,000 characters left out]"


def test_fit_without_lines_cuts_anyway() -> None:
    out = fit("x" * 100_000)

    assert len(out) <= OUTPUT_LIMIT
    assert out.startswith("x")
    assert out.endswith("x")


def test_fit_names_the_archived_output() -> None:
    out = fit("x" * 100_000, archived_as="out-17")

    assert "the whole output is archived as out-17" in out
    assert 'recall(id="out-17", offset=…)' in out
    assert len(out) <= OUTPUT_LIMIT


def test_fit_takes_another_limit() -> None:
    out = fit("y" * 5_000, 1_000)

    assert len(out) <= 1_000
    assert "[output cut:" in out
