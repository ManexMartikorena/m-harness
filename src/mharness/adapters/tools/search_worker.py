"""The child process where `grep` runs the model's regex (final audit,
2026-10-23, decision of the maintainer).

It reads requests in JSON, one per line, from stdin, and writes for each
one the matches, or the error for the model, in one line of JSON to
stdout, until stdin closes. The parent kills it if it takes too long: a
regex like "(a+)+$" can take exponential time. One child serves a whole
search (audit after hito 10, H3).
"""

import json
import re
import sys

from mharness.adapters.tools.files import compile_pattern, search_files
from mharness.domain.tools import ToolError


def main() -> None:
    compiled: dict[str, re.Pattern[str]] = {}
    for line in sys.stdin:
        request = json.loads(line)
        pattern = request["pattern"]
        try:
            if pattern not in compiled:
                compiled[pattern] = compile_pattern(pattern)
            answer: dict[str, object] = {
                "matches": search_files(
                    compiled[pattern],
                    request["files"],
                    request["raw"],
                    request["max_bytes"],
                    request["max_matches"],
                )
            }
        except ToolError as exc:
            answer = {"error": str(exc)}
        sys.stdout.write(json.dumps(answer) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
