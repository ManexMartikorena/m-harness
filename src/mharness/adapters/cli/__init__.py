"""Terminal adapter: the `maha` command line, the conversation and the
questions before a tool call."""

from mharness.adapters.cli.app import fail, parse
from mharness.adapters.cli.approval import DenyAll, TerminalApproval
from mharness.adapters.cli.commands import parse_command, project_note, prompt_notes
from mharness.adapters.cli.conversation import converse, title_failed
from mharness.adapters.cli.headless import drop_output, print_mode
from mharness.adapters.cli.init import Init
from mharness.adapters.cli.input import StdinLines
from mharness.adapters.cli.questions import TerminalQuestions
from mharness.adapters.cli.reports import eval_report, models_report, run_line
from mharness.adapters.cli.spinner import use_color
from mharness.adapters.cli.subcommands import (
    delete_session,
    export_session,
    import_session,
    list_sessions,
    show_prompt,
    show_stats,
    show_trace,
)

__all__ = [
    "DenyAll",
    "Init",
    "StdinLines",
    "TerminalApproval",
    "TerminalQuestions",
    "converse",
    "delete_session",
    "drop_output",
    "eval_report",
    "export_session",
    "fail",
    "import_session",
    "list_sessions",
    "models_report",
    "parse",
    "parse_command",
    "print_mode",
    "project_note",
    "prompt_notes",
    "run_line",
    "show_prompt",
    "show_stats",
    "show_trace",
    "title_failed",
    "use_color",
]
