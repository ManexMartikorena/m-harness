"""A session in Markdown, for `maha export` and `/export` (spec hito 8,
§1.15).

```
# ¿Qué dice el README?

- Session: `20261030-101500-3fa2`, started 2026-10-30 10:15 UTC
…
## User
…
## maha
…
**→ read_file**
```

For a person to read or share. Long tool results are cut: the JSON of
`maha export --format json` keeps everything.
"""

import re

from mharness.adapters.cli.text import usd
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.session import Session

# Lines of a tool result in Markdown, at most.
MAX_RESULT_LINES = 40

_BACKTICKS = re.compile(r"`+")


def markdown(session: Session) -> str:
    """The conversation of `session`, with what it was and what it cost."""
    header = session.header
    first = next((m.text for m in session.messages if m.role == "user"), "")
    title = first.split("\n", 1)[0].strip() or "Session"
    usage = session.usage
    tokens = f"{usage.input_tokens} in · {usage.output_tokens} out"
    cost = _cost(session)
    lines = [
        f"# {title}",
        "",
        f"- Session: `{header.id}`, started {header.created_at:%Y-%m-%d %H:%M %Z}",
        f"- Directory: `{header.cwd}`",
        f"- Model: `{session.model}` ({header.provider})",
        f"- Tokens: {tokens}" + (f" · {cost}" if cost else ""),
    ]
    # The name of each call, for its result.
    names: dict[str, str] = {}
    speaker = ""
    for message in session.messages:
        now = "User" if message.role == "user" else "maha"
        if now != speaker:
            lines += ["", f"## {now}"]
            speaker = now
        lines += _blocks(message, names)
        if message.interrupted:
            lines += ["", "_(interrupted)_"]
    return "\n".join(lines) + "\n"


def _blocks(message: Message, names: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for block in message.blocks:
        match block:
            case TextBlock(text=text) if text.strip():
                lines += ["", text.strip("\n")]
            case ToolCallBlock(id=call_id, name=name, arguments=arguments):
                names[call_id] = name
                lines += ["", f"**→ {name}**", ""]
                lines += _fenced(arguments.strip() or "{}", "json")
            case ToolResultBlock(call_id=call_id, content=content, is_error=failed):
                mark = "✗" if failed else "✓"
                lines += ["", f"**{mark} {names.get(call_id, 'tool')}**", ""]
                shown = content.split("\n")
                lines += _fenced("\n".join(shown[:MAX_RESULT_LINES]))
                if len(shown) > MAX_RESULT_LINES:
                    more = len(shown) - MAX_RESULT_LINES
                    lines += [
                        "",
                        f"_({more} more lines; maha export --format json has "
                        "them all)_",
                    ]
    return lines


def _fenced(text: str, language: str = "") -> list[str]:
    """`text` in a code block whose fence no run of backticks in it closes."""
    longest = max((len(run) for run in _BACKTICKS.findall(text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}{language}", text, fence]


def _cost(session: Session) -> str:
    """What it cost; a minimum (≥) if some turn had no price, and nothing
    if none had."""
    if not session.uncosted_turns:
        return usd(session.cost)
    if session.cost:
        return f"≥{usd(session.cost)}"
    return ""
