"""Wildcards in linear time (deep audit after hito 9, H1)."""

import time
from itertools import product
from pathlib import PurePath

from mharness.domain.wildcard import glob_matches

PATTERNS = [
    "*.py",
    "**/*.py",
    "src/**/*.py",
    "src/*/*.py",
    "**/sub/*",
    "src/**",
    "**",
    "*",
    "a?c",
    "[ab]*/x",
    "src/[!n]*",
    "**/a/**/b",
]
PATHS = [
    "main.py",
    "src/app.py",
    "src/sub/util.py",
    "src/notes.md",
    "abc",
    "a/x",
    "b/q/x",
    "a/b",
    "a/c/d/b",
    "x/a/b",
]


def test_it_says_what_full_match_says() -> None:
    for pattern, path in product(PATTERNS, PATHS):
        expected = PurePath(path).full_match(pattern)
        assert glob_matches(pattern, PurePath(path)) == expected, (pattern, path)


def test_a_hostile_pattern_answers_at_once() -> None:
    started = time.monotonic()

    found = glob_matches("**/*a*a*a*a*a*a*a*a*a*a*a*a*b", PurePath("x/" + "a" * 250))

    assert not found
    assert time.monotonic() - started < 1.0
