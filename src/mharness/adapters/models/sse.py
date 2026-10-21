"""Server-Sent Events, parsed by hand (spec hito 3, §1.3).

Implements the part of the WHATWG rules that a model stream needs: `data`
fields, comments and blank lines. `event`, `id` and `retry` are ignored.
"""

import re
from collections.abc import AsyncIterator

from mharness.domain.errors import ModelResponseError

# Limit for an unfinished line or an event's data, in characters. A real chunk
# is hundreds of bytes; this bounds memory against a broken server.
MAX_SIZE = 1024 * 1024

# Only CR and LF end a line. str.splitlines() also splits at U+2028 and
# others, which may appear raw inside a JSON string.
_LINE_END = re.compile(r"\r\n|\r|\n")


async def parse_sse(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
    """Yield the data of each event. `chunks` is decoded text, any size."""
    pending = ""
    data = ""
    async for chunk in chunks:
        pending += chunk
        lines, pending = _split_lines(pending)
        for line in lines:
            data, event = _process(line, data)
            if event is not None:
                yield event
        if len(pending) > MAX_SIZE:
            raise ModelResponseError("a stream line is too long")
    # A CR kept at the end, waiting for a possible LF, ends its line.
    if pending.endswith("\r"):
        _, event = _process(pending[:-1], data)
        if event is not None:
            yield event
    # Anything else not dispatched is discarded, as the standard says.


def _split_lines(text: str) -> tuple[list[str], str]:
    """Complete lines and the unfinished rest.

    A CR at the very end stays in the rest: if the next chunk starts with LF,
    the two are one line ending.
    """
    lines: list[str] = []
    start = 0
    for match in _LINE_END.finditer(text):
        if match.group() == "\r" and match.end() == len(text):
            break
        lines.append(text[start : match.start()])
        start = match.end()
    return lines, text[start:]


def _process(line: str, data: str) -> tuple[str, str | None]:
    """Apply one line; return the new data buffer and the event, if any."""
    if not line:
        # A blank line dispatches, but only if some data line came before.
        if not data:
            return "", None
        return "", data.removesuffix("\n")
    if line.startswith(":"):
        return data, None
    field, _, value = line.partition(":")
    if field != "data":
        return data, None
    data += value.removeprefix(" ") + "\n"
    if len(data) > MAX_SIZE:
        raise ModelResponseError("a stream event is too large")
    return data, None
