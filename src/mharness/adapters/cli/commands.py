"""What a line is: a command for maha, or text for the model (spec hito 6,
§1.8)."""

import re
from dataclasses import dataclass

# What each command does, for /help.
COMMANDS = {
    "sessions": "/sessions — the recent sessions, of every directory",
    "resume": "/resume [ID] — resume a session; without ID, the last one here",
    "delete": "/delete ID — delete a session",
    "model": "/model [ID] — show the model, or change it",
    "help": "/help — this list",
    "exit": "/exit — quit",
}
# "/" and lowercase letters, as the first word: "/etc/hosts …" is text.
_NAME = re.compile(r"/([a-z]+)")


@dataclass(frozen=True)
class Command:
    name: str
    argument: str | None


def parse_command(line: str) -> Command | None:
    """The command in `line`, known or not; None if it goes to the model."""
    first, _, rest = line.partition(" ")
    match = _NAME.fullmatch(first)
    if match is None:
        return None
    return Command(match.group(1), rest.strip() or None)
