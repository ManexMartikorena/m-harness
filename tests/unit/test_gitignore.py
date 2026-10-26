"""`.gitignore` rules, as gitignore(5) describes them (spec
mejora-2026-10-23-deuda-hito-5, E6), without the disk."""

from pathlib import PurePath

import pytest

from mharness.domain.gitignore import GitIgnore


def ignores(text: str, path: str, *, is_dir: bool = False, base: str = "") -> bool:
    rules = GitIgnore()
    rules.add(PurePath(base), text)
    return rules.ignores(PurePath(path), is_dir=is_dir)


@pytest.mark.parametrize(
    ("pattern", "path", "is_dir", "ignored"),
    [
        # Without "/": the name, at any depth.
        ("*.log", "a.log", False, True),
        ("*.log", "src/deep/a.log", False, True),
        ("*.log", "a.log.txt", False, False),
        ("build", "build", True, True),
        ("build", "src/build", True, True),
        # A "/" at the start or in the middle anchors to the .gitignore.
        ("/build", "build", True, True),
        ("/build", "src/build", True, False),
        ("doc/*.txt", "doc/a.txt", False, True),
        ("doc/*.txt", "doc/sub/a.txt", False, False),
        ("doc/*.txt", "x/doc/a.txt", False, False),
        # A "/" at the end: only directories.
        ("out/", "out", True, True),
        ("out/", "out", False, False),
        # "**".
        ("**/cache", "a/b/cache", True, True),
        ("**/cache", "cache", True, True),
        ("logs/**", "logs/a/b.txt", False, True),
        ("a/**/b", "a/b", False, True),
        ("a/**/b", "a/x/y/b", False, True),
        # "?", "[...]" and "\".
        ("?.txt", "a.txt", False, True),
        ("?.txt", "ab.txt", False, False),
        ("[ab].txt", "b.txt", False, True),
        ("[!ab].txt", "c.txt", False, True),
        ("[!ab].txt", "a.txt", False, False),
        ("[]a].txt", "].txt", False, True),
        ("[!]a].txt", "b.txt", False, True),
        ("[!]a].txt", "].txt", False, False),
        # Corrected 2026-10-26 (B7): git matches nothing with an unclosed "[".
        ("[a", "[a", False, False),
        ("\\#notes", "#notes", False, True),
        ("\\!important", "!important", False, True),
        ("name\\ ", "name ", False, True),
        ("a.txt   ", "a.txt", False, True),
        # "*" does not cross a "/".
        ("src*", "src/a.py", False, False),
    ],
)
def test_one_pattern(pattern: str, path: str, is_dir: bool, ignored: bool) -> None:
    assert ignores(pattern, path, is_dir=is_dir) is ignored


def test_comments_and_blank_lines_are_skipped() -> None:
    assert not ignores("# a.txt\n\n   \n", "a.txt")
    assert not ignores("# a.txt\n", "# a.txt")


def test_the_last_matching_rule_wins_and_can_negate() -> None:
    text = "*.log\n!keep.log\n"

    assert ignores(text, "a.log")
    assert not ignores(text, "keep.log")
    assert ignores(text + "keep.log\n", "keep.log")


def test_rules_of_a_deeper_file_are_relative_to_it() -> None:
    rules = GitIgnore()
    rules.add(PurePath(""), "*.tmp\n")
    rules.add(PurePath("sub"), "/data\n!x.tmp\n")

    assert rules.ignores(PurePath("sub/data"), is_dir=True)
    assert not rules.ignores(PurePath("data"), is_dir=True)
    assert not rules.ignores(PurePath("sub/x.tmp"), is_dir=False)
    assert rules.ignores(PurePath("x.tmp"), is_dir=False)
    # A file does not apply to its own folder.
    assert not rules.ignores(PurePath("sub"), is_dir=True)


def test_crlf_files_are_read() -> None:
    assert ignores("*.log\r\nbuild/\r\n", "build", is_dir=True)


# Rare cases, as `git check-ignore --no-index` (git 2.53.0) answered them on
# 2026-10-26 (spec mejora-2026-10-26-deuda-pre-hito-6, B7). CI does not call
# git: the answers are kept here.
@pytest.mark.parametrize(
    ("pattern", "path", "ignored"),
    [
        # POSIX classes.
        ("a[[:digit:]]", "a1", True),
        ("a[[:digit:]]", "ab", False),
        ("a[[:digit:]]", "a[", False),
        ("f[[:alpha:]]x", "fbx", True),
        ("f[[:alpha:]]x", "f1x", False),
        ("[[:space:]]", " ", True),
        ("[[:space:]]", "x", False),
        # "\" escapes inside a class.
        ("[\\]]r", "]r", True),
        ("[\\]]r", "\\r", False),
        ("[\\]]r", "xr", False),
        # A "[" that never closes matches nothing.
        ("s[", "s[", False),
        ("s[", "s", False),
        ("ab[c", "ab[c", False),
        ("ab[c", "abc", False),
        # A "\" at the end matches nothing.
        ("x\\", "x\\", False),
        ("x\\", "x", False),
        # "\\" is a "\": the space after it is not escaped, and goes.
        ("trail\\\\ ", "trail\\", True),
        ("trail\\\\ ", "trail\\ ", False),
        ("trail\\\\ ", "trail", False),
        ("sp\\ ", "sp ", True),
        ("sp\\ ", "sp", False),
        # A "]" first is part of the class, also negated; "-" at the end too.
        ("[!]a]", "b", True),
        ("[!]a]", "]", False),
        ("[!]a]", "a", False),
        ("[a-]", "a", True),
        ("[a-]", "-", True),
        ("[a-]", "b", False),
    ],
)
def test_like_git(pattern: str, path: str, ignored: bool) -> None:
    assert ignores(pattern, path) is ignored
