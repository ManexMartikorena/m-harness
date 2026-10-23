"""No invisible bidi or control characters in the code (final audit,
2026-10-23): they would make a reviewer read something else ("Trojan
Source"). Escape them as \\uXXXX."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
HIDDEN = re.compile(
    "[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)
FILES = sorted(
    [*ROOT.glob("src/**/*.py"), *ROOT.glob("tests/**/*.py"), *ROOT.glob("docs/**/*.md")]
)


@pytest.mark.parametrize("path", FILES, ids=lambda path: str(path.relative_to(ROOT)))
def test_no_hidden_characters(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    found = [
        f"line {text.count(chr(10), 0, match.start()) + 1}: U+{ord(match.group()):04X}"
        for match in HIDDEN.finditer(text)
    ]
    assert found == []
