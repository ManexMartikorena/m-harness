"""Command-line parsing for `maha`."""

import argparse
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from mharness import __version__
from mharness.adapters.cli.text import clean

# How `-p` writes its result (spec hito 8, §1.11).
OUTPUT_FORMATS = ("text", "json", "stream-json")
# The options of a conversation, and how each one is named in an error.
_CONVERSATION = {
    "prompt": "-p",
    "last": "-c",
    "session": "-r",
    "model": "-m",
    "output_format": "--output-format",
    "allow": "--allow",
    "max_steps": "--max-steps",
    "max_cost": "--max-cost",
    "max_tokens": "--max-tokens",
    "timeout": "--timeout",
}
# Only without a person: the others also go with the conversation.
_PRINT_ONLY = ("output_format", "allow")


def build_parser(tools: Sequence[str]) -> argparse.ArgumentParser:
    """`tools` are the names `--allow` takes."""
    parser = argparse.ArgumentParser(
        prog="maha",
        description="A general-purpose terminal agent, built from scratch. "
        "Without a command, a conversation; with -p, one instruction.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    _conversation_options(parser, tools)
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    _eval_parser(commands)
    return parser


def _conversation_options(
    parser: argparse.ArgumentParser, tools: Sequence[str]
) -> None:
    """`maha -p` and what a conversation takes (spec hito 8, §1.13)."""
    parser.add_argument(
        "-p",
        "--print",
        dest="prompt",
        nargs="?",
        const="",
        metavar="TEXT",
        help="do TEXT and exit; piped input goes below it, or is the "
        "instruction without TEXT",
    )
    resume = parser.add_mutually_exclusive_group()
    resume.add_argument(
        "-c",
        "--continue",
        dest="last",
        action="store_true",
        help="continue the last session of this directory",
    )
    resume.add_argument(
        "-r",
        "--resume",
        dest="session",
        nargs="?",
        # Without the id, or with an empty one, the error says where to
        # find one (spec §1.12).
        const="",
        type=str.strip,
        metavar="ID",
        help="resume a session",
    )
    parser.add_argument(
        "-m", "--model", type=_text, metavar="ID", help="the model of this run"
    )
    parser.add_argument(
        "--output-format",
        choices=OUTPUT_FORMATS,
        help="with -p: only the answer (text, default), one JSON object "
        "(json), or one per event (stream-json)",
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        choices=tools,
        metavar="TOOL",
        help="with -p: run this tool's calls in this directory without "
        "asking; repeatable. Outside it, secrets and files that run code "
        f"are always denied. Tools: {', '.join(tools)}",
    )
    parser.add_argument(
        "--max-steps", type=_positive, metavar="N", help="calls to the model per turn"
    )
    parser.add_argument("--max-cost", type=_usd, metavar="USD", help="dollars per turn")
    parser.add_argument(
        "--max-tokens",
        type=_positive,
        metavar="N",
        help="input and output tokens per turn",
    )
    parser.add_argument(
        "--timeout", type=_seconds, metavar="S", help="seconds per turn"
    )


def _eval_parser(commands: Any) -> None:
    """`maha eval` (spec hito 8, §1.8 and §1.9)."""
    evals = commands.add_parser(
        "eval",
        help="run the eval battery, with real calls",
        description="Run the eval battery of maha's repository and compare "
        "it with the last baseline of each model. Makes real calls.",
    )
    evals.add_argument(
        "--tasks", default="evals", metavar="DIR", help="the battery (default: evals)"
    )
    evals.add_argument(
        "--models",
        type=_models,
        metavar="A,B",
        help="models of the configured provider (default: the configured one)",
    )
    evals.add_argument(
        "--repeat", type=_positive, default=1, metavar="N", help="runs of each task"
    )
    evals.add_argument(
        "--jobs", type=_positive, default=4, metavar="N", help="runs at once"
    )
    evals.add_argument("--split", choices=["train", "validation", "all"], default="all")
    evals.add_argument(
        "--only", action="append", default=[], metavar="ID", help="only this task"
    )
    evals.add_argument(
        "--save", action="store_true", help="keep the result as the new baseline"
    )
    evals.add_argument(
        "--keep", action="store_true", help="keep each run's copy of its repository"
    )
    evals.add_argument(
        "--retry-errors",
        action="store_true",
        help="run once more what the provider broke (429, 5xx, network)",
    )


def _positive(text: str) -> int:
    try:
        number = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def _usd(text: str) -> Decimal:
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"not an amount: {text!r}") from None
    if not amount.is_finite() or amount < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return amount


def _seconds(text: str) -> float:
    try:
        seconds = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    # NaN fails both: it is not more than 0.
    if not 0 < seconds < float("inf"):
        raise argparse.ArgumentTypeError("must be more than 0")
    return seconds


def _text(text: str) -> str:
    if not text.strip():
        raise argparse.ArgumentTypeError("empty")
    return text.strip()


def _models(text: str) -> list[str]:
    models = [model.strip() for model in text.split(",") if model.strip()]
    if not models:
        raise argparse.ArgumentTypeError("no model given")
    return models


def parse(
    argv: Sequence[str] | None = None, *, tools: Sequence[str]
) -> argparse.Namespace | int:
    """The options, or the exit code if the command line already finished.

    `--version` and `--help` end here (0), as do usage errors (2): also
    the options that do not go together.
    """
    parser = build_parser(tools)
    try:
        options = parser.parse_args(argv)
        _check(parser, options)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 1
    return options


def _check(parser: argparse.ArgumentParser, options: argparse.Namespace) -> None:
    """What argparse cannot say: which options need -p, and that a command
    takes none of the conversation's."""
    given = [
        flag
        for name, flag in _CONVERSATION.items()
        if getattr(options, name) not in (None, False, [])
    ]
    if options.session == "":
        parser.error("-r needs the id of a session: /sessions lists them")
    if options.command is not None and given:
        parser.error(f"{options.command} does not take {', '.join(given)}")
    if options.prompt is None:
        alone = [_CONVERSATION[name] for name in _PRINT_ONLY]
        alone = [flag for flag in alone if flag in given]
        if alone:
            verb = "goes" if len(alone) == 1 else "go"
            parser.error(f"{' and '.join(alone)} only {verb} with -p")
    if options.output_format is None:
        options.output_format = "text"


def fail(message: str) -> int:
    """Report an error that stops `maha` before the conversation opens."""
    print(f"error: {clean(message)}", file=sys.stderr)
    return 1
