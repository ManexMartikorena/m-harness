"""The local command runner (spec hito 5, §1.9 and §4.5): real commands, all
harmless."""

import ast
import asyncio
import contextlib
import os
import pty
import select
import signal
import sys
import time
from pathlib import Path

import pytest

from mharness.adapters.commands import LocalCommandRunner
from mharness.domain.commands import OUTPUT_MAX_CHARS, CommandResult
from mharness.domain.environment import command_env
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


# Run in a process that has a terminal, as `maha` in a console: the result
# of one command, printed.
IN_A_TERMINAL = """
import asyncio, os, sys
from pathlib import Path
from mharness.adapters.commands import LocalCommandRunner
result = asyncio.run(LocalCommandRunner().run(
    sys.argv[1], cwd=Path(sys.argv[2]), time_limit=5,
    env={"PATH": os.environ["PATH"]},
))
print(repr((result.exit_code, result.timed_out)), flush=True)
"""


def run_in_a_terminal(command: str, cwd: Path) -> tuple[str, float]:
    """What the command gave, run by `maha` from a terminal, and how long it
    took."""
    started = time.monotonic()
    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover (the child)
        os.execv(
            sys.executable, [sys.executable, "-c", IN_A_TERMINAL, command, str(cwd)]
        )
    out = b""
    try:
        while select.select([fd], [], [], 20)[0]:
            try:
                chunk = os.read(fd, 4096)
            except OSError:  # the terminal closes when the child ends
                break
            if not chunk:
                break
            out += chunk
    finally:
        os.close(fd)
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    return out.decode(errors="replace").strip(), time.monotonic() - started


def test_a_command_cannot_wait_on_the_terminal(tmp_path: Path) -> None:
    # `sudo`, `ssh` or `gpg` ask for a password on /dev/tty, not on stdin: in
    # the same session as `maha`, the command stopped there until the time
    # limit (found 2026-10-27). Without a terminal it fails at once.
    output, took = run_in_a_terminal("read x < /dev/tty", tmp_path)
    exit_code, timed_out = ast.literal_eval(output)

    assert exit_code not in (0, None)
    assert not timed_out
    assert took < 4


async def test_git_commit_without_a_message_fails_at_once_and_clean(
    tmp_path: Path,
) -> None:
    # With the variables `maha` gives: no editor opens, and the model reads
    # a clear error instead of terminal codes (found 2026-10-27).
    git = "git -c user.name=Ane -c user.email=ane@example.com"
    result = await LocalCommandRunner().run(
        f"git init -q && touch a && git add a && {git} commit",
        cwd=tmp_path,
        time_limit=10,
        env=command_env(
            {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "TERM": "xterm"}
        ),
    )

    assert (result.exit_code, result.timed_out) == (1, False)
    assert "empty commit message" in result.output
    assert "\x1b" not in result.output


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


async def test_a_background_child_does_not_make_it_wait_for_the_limit(
    tmp_path: Path,
) -> None:
    # The child keeps the pipe open; the command still ends when its shell
    # does, and the child goes with the group (final audit, 2026-10-23).
    pidfile = tmp_path / "pid"
    started = asyncio.get_running_loop().time()

    result = await run(f"echo hola; sleep 30 & echo $! > {pidfile}", tmp_path, 20)

    assert asyncio.get_running_loop().time() - started < 5
    assert result == CommandResult(
        exit_code=0, output="hola\n", truncated=False, timed_out=False
    )
    assert await gone(int(pidfile.read_text()))


async def test_a_process_that_leaves_the_group_does_not_survive(tmp_path: Path) -> None:
    # `setsid` leaves the process group, so killpg misses it. maha adopts the
    # orphans (subreaper) and kills what is left of the command (decision of
    # the maintainer, 2026-10-23: E2 comes forward from the sandbox, now hito 15).
    pidfile = tmp_path / "pid"

    result = await run(
        f"setsid sleep 30 > /dev/null 2>&1 & echo $! > {pidfile}", tmp_path
    )

    assert result.exit_code == 0
    assert await gone(await written_pid(pidfile))


async def test_an_escaped_process_dies_on_ctrl_c_too(tmp_path: Path) -> None:
    pidfile = tmp_path / "pid"
    task = asyncio.ensure_future(
        run(
            f"setsid sleep 30 > /dev/null 2>&1 & echo $! > {pidfile}; sleep 30",
            tmp_path,
            30,
        )
    )
    escaped = await written_pid(pidfile)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await gone(escaped)


async def test_an_escaped_process_that_cannot_be_killed_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One of another user (`sudo … &`): the command still gives its result,
    # as `_kill_group` already does (end-of-session audit, 2026-10-23).
    pidfile = tmp_path / "pid"
    real_kill = os.kill

    def refuse(pid: int, sig: int) -> None:
        if sig == signal.SIGKILL:
            raise PermissionError(1, "Operation not permitted")
        real_kill(pid, sig)

    monkeypatch.setattr(os, "kill", refuse)
    try:
        result = await run(
            f"setsid sleep 30 > /dev/null 2>&1 & echo $! > {pidfile}; echo hola",
            tmp_path,
        )
    finally:
        monkeypatch.undo()
        if (pid := read_pid(pidfile)) is not None:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)

    assert (result.exit_code, result.output) == (0, "hola\n")


async def test_a_process_with_a_name_that_is_not_ascii(tmp_path: Path) -> None:
    # Any process of the machine named "ñandú" made every command fail: its
    # /proc/<pid>/stat was read as ASCII (found 2026-10-27).
    rename = "open('/proc/self/comm', 'w').write('ñandú'); print(flush=True); input()"
    other = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        rename,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        assert other.stdout is not None
        await other.stdout.readline()

        result = await run("echo hola", tmp_path)
    finally:
        other.kill()
        await other.wait()

    assert (result.exit_code, result.output) == (0, "hola\n")
