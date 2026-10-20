import tomllib
from pathlib import Path

import pytest

from mharness.adapters import cli

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def test_version_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.run(["--version"])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("maha ")


def test_version_matches_pyproject(capsys: pytest.CaptureFixture[str]) -> None:
    expected = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"][
        "version"
    ]

    cli.run(["--version"])

    assert capsys.readouterr().out == f"maha {expected}\n"


def test_no_arguments_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.run([])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("usage: maha")
    assert "--version" in out


def test_unknown_option_exits_with_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.run(["--nope"])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "unrecognized arguments: --nope" in captured.err
