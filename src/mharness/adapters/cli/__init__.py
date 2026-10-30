"""Terminal adapter: the `maha` command line, the conversation and the
questions before a tool call."""

from mharness.adapters.cli.app import fail, parse
from mharness.adapters.cli.approval import DenyAll, TerminalApproval
from mharness.adapters.cli.conversation import converse
from mharness.adapters.cli.headless import print_mode
from mharness.adapters.cli.input import StdinLines
from mharness.adapters.cli.reports import eval_report, models_report, run_line
from mharness.adapters.cli.spinner import use_color
from mharness.adapters.cli.subcommands import delete_session, list_sessions

__all__ = [
    "DenyAll",
    "StdinLines",
    "TerminalApproval",
    "converse",
    "delete_session",
    "eval_report",
    "fail",
    "list_sessions",
    "models_report",
    "parse",
    "print_mode",
    "run_line",
    "use_color",
]
