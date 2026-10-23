"""The local command runner (spec hito 5, §1.9 and §4.5): real commands, all
harmless."""

import asyncio
import os
from pathlib import Path

import pytest

from mharness.adapters.commands import LocalCommandRunner
from mharness.adapters.commands.local import OUTPUT_MAX_CHARS
from mharness.domain.commands import CommandResult
from mharness.ports.commands import CommandRunner

ENV = {"PATH": os.environ["PATH"]}


async def run(command: str, cwd: Path, time_limit: float = 10) -> CommandResult:
    return await LocalCommandRunner().run(
        command, cwd=cwd, time_limit=time_limit, env=ENV
    )


def test_satisfies_the_port() -> None:
    # mypy checks this assignment against the Protocol.
    runner: CommandRunner = LocalCommandRunner()

    assert runner is not None


async def test_output_and_exit_code_with_stderr_interleaved(tmp_path: Path) -> None:
    result = await run(
        "printf 'a\\n'; printf 'b\\n' >&2; printf 'c\\n'; exit 3", tmp_path
    )

    assert result == CommandResult(
        exit_code=3, output="a\nb\nc\n", truncated=False, timed_out=False
    )


async def test_it_runs_in_the_directory_given(tmp_path: Path) -> None:
    (tmp_path / "here.txt").write_text("")

    result = await run("ls", tmp_path)

    assert result.output == "here.txt\n"


async def test_stdin_is_closed(tmp_path: Path) -> None:
    # A command that reads its input does not wait for it.
    result = await run("cat; echo fin", tmp_path, time_limit=5)

    assert (result.output, result.timed_out) == ("fin\n", False)


async def test_a_long_output_is_cut_without_blocking(tmp_path: Path) -> None:
    # Far more than the pipe holds: the rest is read and thrown away.
    result = await run("head -c 2000000 /dev/zero | tr '\\0' x; echo; exit 0", tmp_path)

    assert result.truncated
    assert result.exit_code == 0
    assert result.output == "x" * OUTPUT_MAX_CHARS


async def test_past_the_time_limit_it_is_killed_keeping_its_output(
    tmp_path: Path,
) -> None:
    result = await run("printf 'antes\\n'; sleep 30", tmp_path, time_limit=0.5)

    assert result == CommandResult(
        exit_code=None, output="antes\n", truncated=False, timed_out=True
    )


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def gone(pid: int) -> bool:
    for _ in range(100):
        if not alive(pid):
            return True
        await asyncio.sleep(0.02)
    return False


def read_pid(path: Path) -> int | None:
    text = path.read_text().strip() if path.exists() else ""
    return int(text) if text else None


async def written_pid(path: Path) -> int:
    """The pid the command writes to `path`, once it is there."""
    for _ in range(500):
        if (pid := read_pid(path)) is not None:
            return pid
        await asyncio.sleep(0.01)
    raise AssertionError(f"no pid in {path}")


async def test_cancelling_kills_the_whole_group(tmp_path: Path) -> None:
    # A grandchild in the background does not survive Ctrl+C.
    pidfile = tmp_path / "pid"
    task = asyncio.ensure_future(
        run(f"sleep 30 & echo $! > {pidfile}; wait", tmp_path, time_limit=30)
    )
    grandchild = await written_pid(pidfile)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await gone(grandchild)


async def test_the_group_is_killed_after_a_normal_end(tmp_path: Path) -> None:
    # Nothing of the command is left running once it returns.
    pidfile = tmp_path / "pid"

    await run(f"sleep 30 > /dev/null 2>&1 & echo $! > {pidfile}", tmp_path)

    assert await gone(int(pidfile.read_text()))


async def test_the_command_gets_exactly_the_env_given(tmp_path: Path) -> None:
    result = await LocalCommandRunner().run(
        "env", cwd=tmp_path, time_limit=5, env={**ENV, "MAHA_X": "1"}
    )

    names = {line.split("=", 1)[0] for line in result.output.splitlines()}
    assert "MAHA_X" in names
    assert "HOME" not in names
