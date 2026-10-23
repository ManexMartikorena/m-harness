"""`run_command` (spec hito 5, §1.9 and §4.5.6), with `FakeRunner`."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from mharness.adapters.tools import RunCommand
from mharness.adapters.tools.shell import RunCommandParams
from mharness.domain.approval import ApprovalRequest
from mharness.domain.commands import CommandResult
from mharness.ports.tools import Tool
from tests.fakes.commands import FakeRunner, Ran

ENV = {"PATH": "/usr/bin"}


def result(
    output: str = "",
    exit_code: int | None = 0,
    *,
    truncated: bool = False,
    timed_out: bool = False,
) -> CommandResult:
    return CommandResult(
        exit_code=exit_code, output=output, truncated=truncated, timed_out=timed_out
    )


def tool(root: Path, *results: CommandResult) -> tuple[RunCommand, FakeRunner]:
    runner = FakeRunner(results)
    return RunCommand(root, runner, ENV), runner


def test_satisfies_the_port(tmp_path: Path) -> None:
    # mypy checks this assignment against the Protocol.
    subject: Tool[RunCommandParams] = tool(tmp_path)[0]

    assert (subject.name, subject.permission) == ("run_command", "effect")
    # The exact description of spec hito 5, §3.2.
    assert subject.description == (
        "Run a shell command in the working directory, with a timeout. "
        'The user approves it first. Example: {"command": "uv run pytest -q"}'
    )


def test_the_timeout_goes_from_1_to_600_seconds() -> None:
    assert RunCommandParams(command="ls").timeout == 120
    for wrong in (0, 601):
        with pytest.raises(ValidationError):
            RunCommandParams(command="ls", timeout=wrong)
    with pytest.raises(ValidationError):
        RunCommandParams(command="")


async def test_it_asks_with_the_command_and_its_exact_scope(tmp_path: Path) -> None:
    subject, _ = tool(tmp_path)

    request = await subject.approval(RunCommandParams(command="uv run pytest -q"))

    assert request == ApprovalRequest(
        tool="run_command",
        title="run: uv run pytest -q",
        detail=(
            f"in {tmp_path}\nwith your permissions: it can change any file you can"
        ),
        scope="run_command:uv run pytest -q",
    )


async def test_a_timeout_that_is_not_the_default_is_shown(tmp_path: Path) -> None:
    subject, _ = tool(tmp_path)

    request = await subject.approval(RunCommandParams(command="make", timeout=300))

    assert request is not None
    assert request.detail.splitlines()[1] == "time limit: 300 s"


async def test_it_runs_in_the_root_with_the_env_given(tmp_path: Path) -> None:
    subject, runner = tool(tmp_path, result("hola\n"))

    text = await subject.run(RunCommandParams(command="echo hola", timeout=7))

    assert runner.ran == [Ran("echo hola", tmp_path, 7, ENV)]
    assert text == "exit code: 0\nhola\n"
    assert subject.summary(text) == "exit code 0"


async def test_a_failing_command_is_information_not_an_error(tmp_path: Path) -> None:
    subject, _ = tool(tmp_path, result("no such file\n", 1))

    text = await subject.run(RunCommandParams(command="ls x"))

    assert text == "exit code: 1\nno such file\n"
    assert subject.summary(text) == "exit code 1"


async def test_a_cut_and_a_timeout_are_told(tmp_path: Path) -> None:
    subject, _ = tool(
        tmp_path,
        result("x" * 10, None, truncated=True, timed_out=True),
        result("", 0),
    )

    cut = await subject.run(RunCommandParams(command="yes", timeout=5))
    empty = await subject.run(RunCommandParams(command="true"))

    assert cut == (
        "killed\nxxxxxxxxxx\n… [output cut at 30000 characters]\n[timed out after 5 s]"
    )
    assert subject.summary(cut) == "timed out (cut)"
    assert empty == "exit code: 0\n(no output)"
