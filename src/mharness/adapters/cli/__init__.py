"""Terminal adapter: the `maha` command line, the conversation and the
questions before a tool call."""

from mharness.adapters.cli.app import fail, parse
from mharness.adapters.cli.approval import DenyAll, TerminalApproval
from mharness.adapters.cli.conversation import converse
from mharness.adapters.cli.headless import print_mode
from mharness.adapters.cli.input import StdinLines
from mharness.adapters.cli.reports import eval_report, run_line
from mharness.adapters.cli.spinner import use_color

__all__ = [
    "DenyAll",
    "StdinLines",
    "TerminalApproval",
    "converse",
    "eval_report",
    "fail",
    "parse",
    "print_mode",
    "run_line",
    "use_color",
]
