"""Command-line parsing for `maha`."""

import argparse
from collections.abc import Sequence
from importlib.metadata import version

DISTRIBUTION = "m-harness"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maha",
        description="A general-purpose terminal agent, built from scratch.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version(DISTRIBUTION)}",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return the process exit code."""
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exit_:
        # argparse exits on --version (0) and on usage errors (2).
        return exit_.code if isinstance(exit_.code, int) else 1
    parser.print_help()
    return 0
