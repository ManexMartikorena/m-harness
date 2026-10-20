"""Composition root: the only module that knows every piece.

It builds the adapters, injects them into the application and starts the
`maha` command. In hito 1 there is nothing to wire yet.
"""

from collections.abc import Sequence

from mharness.adapters import cli


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the `maha` command."""
    return cli.run(argv)
