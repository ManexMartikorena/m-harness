"""Terminal adapter: the `maha` command line, the conversation and the
questions before a tool call."""

from mharness.adapters.cli.app import fail, parse
from mharness.adapters.cli.approval import DenyAll, TerminalApproval
from mharness.adapters.cli.conversation import converse
from mharness.adapters.cli.headless import print_mode
from mharness.adapters.cli.input import StdinLines
from mharness.adapters.cli.reports import eval_report, models_report, run_line
from mharness.adapters.cli.spinner import use_color
from mharness.adapters.cli.subcommands import (
    delete_session,
    export_session,
    import_session,
    list_sessions,
    show_stats,
    show_trace,
)

__all__ = [
    "DenyAll",
    "StdinLines",
    "TerminalApproval",
    "converse",
    "delete_session",
    "eval_report",
    "export_session",
    "fail",
    "import_session",
    "list_sessions",
    "models_report",
    "parse",
    "print_mode",
    "run_line",
    "show_stats",
    "show_trace",
    "use_color",
]
