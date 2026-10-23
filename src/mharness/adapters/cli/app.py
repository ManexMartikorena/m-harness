"""Command-line parsing for `maha`."""

import argparse
import sys
from collections.abc import Sequence

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
    return parser


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
