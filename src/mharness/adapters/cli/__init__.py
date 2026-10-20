"""Terminal adapter: the `maha` command line and the conversation."""

from mharness.adapters.cli.app import fail, parse
from mharness.adapters.cli.conversation import converse

__all__ = ["converse", "fail", "parse"]
