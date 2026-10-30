import argparse
import tomllib
from decimal import Decimal
from pathlib import Path

import pytest

from mharness.adapters import cli
from mharness.adapters.cli.text import clean, usd
from mharness.bootstrap import TOOL_NAMES

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def parse(argv: list[str]) -> argparse.Namespace | int:
    return cli.parse(argv, tools=TOOL_NAMES)


def test_version_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = parse(["--version"])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("maha ")


def test_version_matches_pyproject(capsys: pytest.CaptureFixture[str]) -> None:
    expected = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"][
        "version"
    ]

    parse(["--version"])

    assert capsys.readouterr().out == f"maha {expected}\n"


def test_help_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    code = parse(["--help"])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("usage: maha")
    assert "--version" in out


def test_no_arguments_returns_the_options(capsys: pytest.CaptureFixture[str]) -> None:
    # Changes decision 3.3 of hito 1: `maha` alone opens the conversation.
    options = parse([])

    assert isinstance(options, argparse.Namespace)
    assert capsys.readouterr().out == ""


def test_unknown_option_exits_with_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = parse(["--nope"])

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
    options = parse(["eval"])

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
    options = parse(
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
    assert parse(args) == 2
    assert "usage:" in capsys.readouterr().err


def test_without_a_command_there_is_none() -> None:
    options = parse([])

    assert isinstance(options, argparse.Namespace)
    assert options.command is None


# `maha -p` and the options of a conversation (spec hito 8, §1.13).


def test_without_options_the_conversation_has_its_defaults() -> None:
    options = parse([])

    assert isinstance(options, argparse.Namespace)
    assert (options.prompt, options.last, options.session, options.model) == (
        None,
        False,
        None,
        None,
    )
    assert (options.output_format, options.allow) == ("text", [])
    assert (options.max_steps, options.max_cost, options.max_tokens) == (
        None,
        None,
        None,
    )
    assert options.timeout is None


@pytest.mark.parametrize(
    ("args", "prompt"),
    [
        (["-p", "resume este proyecto"], "resume este proyecto"),
        (["--print", "hola"], "hola"),
        # Without text: the instruction comes from stdin.
        (["-p"], ""),
        (["-p", "-c"], ""),
        # A command's name after -p is its text, not the command.
        (["-p", "eval"], "eval"),
    ],
)
def test_print_takes_its_text_or_none(args: list[str], prompt: str) -> None:
    options = parse(args)

    assert isinstance(options, argparse.Namespace)
    assert options.prompt == prompt
    assert options.command is None


def test_print_takes_every_option() -> None:
    options = parse(
        [
            "-p",
            "arregla el test",
            "-r",
            "20261027-101500-3fa2",
            "-m",
            "kimi-k2.7-code",
            "--output-format",
            "json",
            "--allow",
            "edit_file",
            "--allow",
            "write_file",
            "--max-steps",
            "10",
            "--max-cost",
            "0.25",
            "--max-tokens",
            "50000",
            "--timeout",
            "90.5",
        ]
    )

    assert isinstance(options, argparse.Namespace)
    assert (options.session, options.model) == (
        "20261027-101500-3fa2",
        "kimi-k2.7-code",
    )
    assert (options.output_format, options.allow) == (
        "json",
        ["edit_file", "write_file"],
    )
    assert (options.max_steps, options.max_cost, options.max_tokens) == (
        10,
        Decimal("0.25"),
        50000,
    )
    assert options.timeout == 90.5


def test_continue_and_the_limits_go_with_the_conversation() -> None:
    options = parse(["-c", "--max-cost", "0", "--model", "glm-5.3"])

    assert isinstance(options, argparse.Namespace)
    assert (options.last, options.max_cost, options.model) == (
        True,
        Decimal(0),
        "glm-5.3",
    )


@pytest.mark.parametrize(
    ("args", "says"),
    [
        (["--allow", "write_file"], "--allow only goes with -p"),
        (["--output-format", "json"], "--output-format only goes with -p"),
        (
            ["--output-format", "json", "--allow", "read_file"],
            "--output-format and --allow only go with -p",
        ),
        (["-c", "-r", "20261027-101500-3fa2"], "not allowed with argument"),
        (["-p", "x", "--allow", "rm_rf"], "invalid choice: 'rm_rf'"),
        (["-p", "x", "--output-format", "yaml"], "invalid choice: 'yaml'"),
        (["--max-steps", "0"], "must be 1 or more"),
        (["--max-tokens", "x"], "not a number"),
        (["--max-cost", "-1"], "must be 0 or more"),
        (["--max-cost", "NaN"], "must be 0 or more"),
        (["--max-cost", "mucho"], "not an amount"),
        (["--timeout", "0"], "must be more than 0"),
        (["--timeout", "nan"], "must be more than 0"),
        (["--timeout", "inf"], "must be more than 0"),
        (["-m", " "], "empty"),
        (["--fallback-model", ""], "empty"),
        (["--fallback-model", "x", "eval"], "eval does not take --fallback-model"),
        (["-r", " "], "-r needs the id of a session"),
        (["-c", "eval"], "eval does not take -c"),
        (["-m", "x", "--timeout", "5", "eval"], "eval does not take -m, --timeout"),
        # Decimal("0") == False: 0 is given all the same.
        (["--max-cost", "0", "eval"], "eval does not take --max-cost"),
    ],
)
def test_options_that_do_not_go_together_are_a_usage_error(
    args: list[str], says: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert parse(args) == 2
    assert says in capsys.readouterr().err


def test_help_names_the_tools_allow_takes(capsys: pytest.CaptureFixture[str]) -> None:
    parse(["--help"])

    out = " ".join(capsys.readouterr().out.split())
    assert "Tools: read_file, list_dir, glob, grep, write_file, edit_file, " in out
    assert "run_command" in out


def test_resume_without_an_id_says_where_to_find_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert parse(["-r"]) == 2
    assert "-r needs the id of a session: maha sessions lists them" in (
        capsys.readouterr().err
    )


def test_models_lists_the_provider_unless_all() -> None:
    options = parse(["models"])
    assert isinstance(options, argparse.Namespace)
    assert (options.command, options.every) == ("models", False)

    options = parse(["models", "--all"])
    assert isinstance(options, argparse.Namespace)
    assert options.every is True


def test_models_takes_no_conversation_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert parse(["-m", "x", "models"]) == 2
    assert "models does not take -m" in capsys.readouterr().err


def test_sessions_lists_or_deletes() -> None:
    options = parse(["sessions"])
    assert isinstance(options, argparse.Namespace)
    assert (options.command, options.action) == ("sessions", None)

    options = parse(["sessions", "delete", "20261030-101500-3fa2"])
    assert isinstance(options, argparse.Namespace)
    assert (options.action, options.id) == ("delete", "20261030-101500-3fa2")


def test_sessions_delete_needs_the_id(capsys: pytest.CaptureFixture[str]) -> None:
    assert parse(["sessions", "delete"]) == 2
    assert "the following arguments are required: ID" in capsys.readouterr().err


def test_trace_takes_an_optional_id() -> None:
    options = parse(["trace"])
    assert isinstance(options, argparse.Namespace)
    assert (options.command, options.id) == ("trace", None)

    options = parse(["trace", "20261030-101500-3fa2"])
    assert isinstance(options, argparse.Namespace)
    assert options.id == "20261030-101500-3fa2"
