from collections.abc import AsyncIterator

import pytest

from mharness.adapters.models.sse import MAX_SIZE, parse_sse
from mharness.domain.errors import ModelResponseError


async def chunks(*items: str) -> AsyncIterator[str]:
    for item in items:
        yield item


async def parse(*items: str) -> list[str]:
    return [data async for data in parse_sse(chunks(*items))]


async def test_a_blank_line_dispatches_each_event() -> None:
    assert await parse("data: uno\n\ndata: dos\n\n") == ["uno", "dos"]


async def test_several_data_lines_are_joined_with_lf() -> None:
    assert await parse("data: uno\ndata: dos\n\n") == ["uno\ndos"]


async def test_comments_and_other_fields_are_ignored() -> None:
    stream = ": keep-alive\nevent: chunk\nid: 7\nretry: 1000\ndata: uno\n\n"

    assert await parse(stream) == ["uno"]


async def test_only_one_space_is_removed_after_the_colon() -> None:
    assert await parse("data:uno\n\ndata:  dos\n\n") == ["uno", " dos"]


async def test_empty_data_dispatches_an_empty_event() -> None:
    assert await parse("data:\n\ndata\n\n") == ["", ""]


@pytest.mark.parametrize(
    "stream",
    [
        ": comment\n\n",  # a comment and a blank line
        "\n\n",  # two blank lines
        "event: chunk\n\n",  # a lone event field
    ],
)
async def test_nothing_is_dispatched_without_a_data_line(stream: str) -> None:
    assert await parse(stream) == []


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
async def test_every_line_ending_works(newline: str) -> None:
    stream = f"data: uno{newline}{newline}data: dos{newline}{newline}"

    assert await parse(stream) == ["uno", "dos"]


async def test_cr_and_lf_split_between_chunks_are_one_line_ending() -> None:
    # If the "\n" counted as a second line ending, the blank line would
    # dispatch "uno" before "dos" arrives.
    assert await parse("data: uno\r", "\ndata: dos\n\n") == ["uno\ndos"]


async def test_a_line_split_between_chunks_comes_out_whole() -> None:
    assert await parse('data: {"te', 'xt": "Hola"}\n', "\n") == ['{"text": "Hola"}']


async def test_unicode_line_separators_do_not_split_a_line() -> None:
    # Fixes decision 1.3: not str.splitlines(), which splits at these.
    text = f'{{"content": "a{chr(0x2028)}b{chr(0x2029)}c{chr(0x85)}d"}}'

    assert await parse(f"data: {text}\n\n") == [text]


async def test_an_event_without_a_final_blank_line_is_discarded() -> None:
    assert await parse("data: uno\n\ndata: dos\n") == ["uno"]


async def test_a_trailing_cr_ends_the_last_line() -> None:
    assert await parse("data: x\r\r") == ["x"]
    assert await parse("data: x\r") == []


async def test_an_unterminated_line_over_the_limit_fails() -> None:
    with pytest.raises(ModelResponseError):
        await parse("data: " + "x" * MAX_SIZE)


async def test_an_event_over_the_limit_fails() -> None:
    line = "data: " + "x" * (MAX_SIZE // 2) + "\n"

    with pytest.raises(ModelResponseError):
        await parse(line, line, line, "\n")
