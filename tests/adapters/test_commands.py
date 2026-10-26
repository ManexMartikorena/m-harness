"""Commands in the terminal: what is a command and what goes to the model
(spec hito 6, §1.8 and §4.7.1)."""

import pytest

from mharness.adapters.cli.commands import COMMANDS, Command, parse_command


@pytest.mark.parametrize(
    ("line", "command"),
    [
        ("/sessions", Command("sessions", None)),
        ("/resume", Command("resume", None)),
        ("/resume 20261025-174233-b01c", Command("resume", "20261025-174233-b01c")),
        ("/delete   20261025-174233-b01c  ", Command("delete", "20261025-174233-b01c")),
        ("/model kimi-k3", Command("model", "kimi-k3")),
        ("/help", Command("help", None)),
        ("/exit", Command("exit", None)),
        # Unknown, but a command: it never goes to the model.
        ("/sesions", Command("sesions", None)),
        # "/" and lowercase letters alone is a command, also "/tmp".
        ("/tmp", Command("tmp", None)),
    ],
)
def test_commands(line: str, command: Command) -> None:
    assert parse_command(line) == command


@pytest.mark.parametrize(
    "line",
    [
        "Hola",
        "/etc/hosts no existe",
        " /help",
        "/Help",
        "/ ",
        "/resume2",
        "¿qué hace /help?",
    ],
)
def test_text_that_goes_to_the_model(line: str) -> None:
    # A path with more than one part, or anything else, is text.
    assert parse_command(line) is None


def test_the_known_commands() -> None:
    assert set(COMMANDS) == {"sessions", "resume", "delete", "model", "help", "exit"}
