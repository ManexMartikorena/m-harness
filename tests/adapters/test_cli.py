import argparse
import tomllib
from decimal import Decimal
from pathlib import Path

import pytest

from mharness.adapters import cli
from mharness.adapters.cli.text import clean, usd

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def test_version_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.parse(["--version"])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("maha ")


def test_version_matches_pyproject(capsys: pytest.CaptureFixture[str]) -> None:
    expected = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"][
        "version"
    ]

    cli.parse(["--version"])

    assert capsys.readouterr().out == f"maha {expected}\n"


def test_help_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.parse(["--help"])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("usage: maha")
    assert "--version" in out


def test_no_arguments_returns_the_options(capsys: pytest.CaptureFixture[str]) -> None:
    # Changes decision 3.3 of hito 1: `maha` alone opens the conversation.
    options = cli.parse([])

    assert isinstance(options, argparse.Namespace)
    assert capsys.readouterr().out == ""


def test_unknown_option_exits_with_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.parse(["--nope"])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "unrecognized arguments: --nope" in captured.err


def test_fail_reports_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.fail("no model configured")

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err == "error: no model configured\n"


def test_fail_escapes_control_characters(capsys: pytest.CaptureFixture[str]) -> None:
    # The message can quote a project's .maha/config.toml, written by anyone
    # (spec mejora-2026-10-23-deuda-hito-5, A2).
    cli.fail("bad model '\x1b[2Jx'")

    assert capsys.readouterr().err == "error: bad model '\\x1b[2Jx'\n"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("a\nb\tc", "a\nb\tc"),
        ("\x1b[31m", "\\x1b[31m"),
        ("\r\x00\x7f\x9b", "\\x0d\\x00\\x7f\\x9b"),
        ("\u202eabc\u2066\u200f", "\\u202eabc\\u2066\\u200f"),
        ("ñ → ✓ 日本", "ñ → ✓ 日本"),
    ],
)
def test_clean_escapes_only_unsafe_characters(text: str, shown: str) -> None:
    assert clean(text) == shown


# usd(): the cost in the terminal (spec hito 7, §1.5; final review).


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        ("0", "$0"),
        ("0.0008", "$0.0008"),
        ("0.00005", "$0.0001"),
        ("0.0000499", "<$0.0001"),
        ("0.000000123", "<$0.0001"),
        ("12.34567", "$12.3457"),
        # Huge: never an error that hides the line.
        ("1E+30", "$1000000000000000000000000000000"),
    ],
)
def test_usd(amount: str, shown: str) -> None:
    assert usd(Decimal(amount)) == shown


# `maha eval` (spec hito 8, §1.8 and §1.9).


def test_eval_has_its_defaults() -> None:
    options = cli.parse(["eval"])

    assert isinstance(options, argparse.Namespace)
    assert options.command == "eval"
    assert (options.tasks, options.models, options.repeat, options.jobs) == (
        "evals",
        None,
        1,
        4,
    )
    assert (options.split, options.only, options.save) == ("all", [], False)
    assert (options.keep, options.retry_errors) == (False, False)


def test_eval_takes_its_options() -> None:
    options = cli.parse(
        [
            "eval",
            "--models",
            "glm-5.3-flash,kimi-k2.7-code",
            "--repeat",
            "5",
            "--jobs",
            "2",
            "--split",
            "train",
            "--only",
            "01-version",
            "--only",
            "06-arreglar-bug",
            "--save",
            "--keep",
            "--retry-errors",
        ]
    )

    assert isinstance(options, argparse.Namespace)
    assert options.models == ["glm-5.3-flash", "kimi-k2.7-code"]
    assert (options.repeat, options.jobs, options.split) == (5, 2, "train")
    assert options.only == ["01-version", "06-arreglar-bug"]
    assert (options.save, options.keep, options.retry_errors) == (True, True, True)


@pytest.mark.parametrize(
    "args",
    [
        ["eval", "--repeat", "0"],
        ["eval", "--jobs", "0"],
        ["eval", "--split", "test"],
        ["eval", "--models", ""],
    ],
)
def test_eval_rejects_wrong_values(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.parse(args) == 2
    assert "usage:" in capsys.readouterr().err


def test_without_a_command_there_is_none() -> None:
    options = cli.parse([])

    assert isinstance(options, argparse.Namespace)
    assert options.command is None
