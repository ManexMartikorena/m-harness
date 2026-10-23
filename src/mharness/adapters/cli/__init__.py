"""Terminal adapter: the `maha` command line, the conversation and the
questions before a tool call."""

from mharness.adapters.cli.app import fail, parse
from mharness.adapters.cli.approval import DenyAll, TerminalApproval
from mharness.adapters.cli.conversation import converse
from mharness.adapters.cli.input import StdinLines
from mharness.adapters.cli.spinner import use_color

__all__ = [
    "DenyAll",
    "StdinLines",
    "TerminalApproval",
    "converse",
    "fail",
    "parse",
    "use_color",
]
