"""The child process where `grep` runs the model's regex (final audit,
2026-10-23, decision of the maintainer).

It reads one request in JSON from stdin and writes the matches, or the
error for the model, in JSON to stdout. The parent kills it if it takes
too long: a regex like "(a+)+$" can take exponential time.
"""

import json
import sys

from mharness.adapters.tools.files import search_files
from mharness.domain.tools import ToolError


def main() -> None:
    request = json.load(sys.stdin)
    try:
        matches = search_files(
            request["pattern"],
            request["files"],
            request["raw"],
            request["max_bytes"],
            request["max_matches"],
        )
    except ToolError as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        return
    json.dump({"matches": matches}, sys.stdout)


if __name__ == "__main__":
    main()
