import argparse
import tomllib
from pathlib import Path

import pytest

from mharness.adapters import cli

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
