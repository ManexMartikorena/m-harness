"""Command-line parsing for `maha`."""

import argparse
import sys
from collections.abc import Sequence
from typing import Any

from mharness import __version__
from mharness.adapters.cli.text import clean


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maha",
        description="A general-purpose terminal agent, built from scratch.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    _eval_parser(commands)
    return parser


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


def _models(text: str) -> list[str]:
    models = [model.strip() for model in text.split(",") if model.strip()]
    if not models:
        raise argparse.ArgumentTypeError("no model given")
    return models


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace | int:
    """The options, or the exit code if the command line already finished.

    `--version` and `--help` end here (0), as do usage errors (2).
    """
    try:
        return build_parser().parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 1


def fail(message: str) -> int:
    """Report an error that stops `maha` before the conversation opens."""
    print(f"error: {clean(message)}", file=sys.stderr)
    return 1
