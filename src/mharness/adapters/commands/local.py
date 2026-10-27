"""Shell commands on this machine (spec hito 5, §1.9).

Each command runs in its own session, and so in its own process group and
without a terminal: Ctrl+C in the terminal does not reach it, a command that
asks for a password on /dev/tty (`sudo`, `ssh`) fails at once instead of
waiting until the time limit (found 2026-10-27), and `maha` kills the whole
group, grandchildren included, when the time is up, when the task is
cancelled, and when its shell ends. No
threads: the output is read with asyncio while the command runs, so a
command that writes a lot never blocks on a full pipe.

A process that leaves the group (`setsid`) is caught too: `maha` becomes a
subreaper, so the orphans of a command become its children instead of
init's, and the ones left when the command ends are killed (decision of the
maintainer, 2026-10-23: it came forward from the sandbox, now hito 15). Linux only.

One command at a time in the whole process: the cleanup takes every child
of `maha` it did not know as escaped, and so killed the commands that
started after it and were still running (found running the evals in
parallel, 2026-10-27). Running several at once needs another way to tell
them apart (hito 16).

It runs with your permissions and no sandbox until hito 15: the defence is
that you read the command before approving it.
"""

import asyncio
import contextlib
import ctypes
import os
import signal
import weakref
from collections.abc import Mapping
from pathlib import Path

from mharness.domain.commands import OUTPUT_MAX_CHARS, CommandResult

# Enough bytes for that many characters in UTF-8; the rest is read and
# thrown away.
_KEPT_BYTES = 4 * OUTPUT_MAX_CHARS
_CHUNK = 64 * 1024
# How often the exit of the shell is checked.
EXIT_POLL_SECONDS = 0.05
# How long the rest of the output is read once the command has ended.
DRAIN_SECONDS = 1.0
# prctl(2): orphans of descendants are re-parented to this process.
PR_SET_CHILD_SUBREAPER = 36
# Rounds to find what is left of a command, and the pause between them.
ESCAPED_ROUNDS = 50
ESCAPED_PAUSE = 0.02


# One lock per event loop, shared by every runner: being the subreaper is
# a matter of the whole process.
_turns: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


class LocalCommandRunner:
    def __init__(self) -> None:
        _become_subreaper()

    async def run(
        self, command: str, *, cwd: Path, time_limit: float, env: Mapping[str, str]
    ) -> CommandResult:
        loop = asyncio.get_running_loop()
        async with _turns.setdefault(loop, asyncio.Lock()):
            return await self._run(command, cwd=cwd, time_limit=time_limit, env=env)

    async def _run(
        self, command: str, *, cwd: Path, time_limit: float, env: Mapping[str, str]
    ) -> CommandResult:
        # Children that are not this command's: they are left alone.
        before = _children()
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            env=dict(env),
            # A command that asks for input does not wait for it.
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            # A new session: a new group, whose id is the pid, and no
            # terminal to wait on.
            start_new_session=True,
        )
        assert process.stdout is not None
        output = _Output()
        reader = asyncio.create_task(output.read(process.stdout))
        timed_out = False
        try:
            try:
                # The command ends when its shell does, even if a child in
                # the background still holds the pipe (final audit,
                # 2026-10-23).
                async with asyncio.timeout(time_limit):
                    await _exited(process)
            except TimeoutError:
                timed_out = True
            _kill_group(process.pid)
            # What is left in the pipe, now that the group is gone. A process
            # that left the group could hold it open: it is not waited for.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(reader), DRAIN_SECONDS)
        finally:
            _kill_group(process.pid)
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
            # Reaped also when cancelled: SIGKILL ends it at once.
            await _exited(process)
            await _kill_escaped(before | {process.pid})
        text = output.kept.decode("utf-8", errors="replace")
        code = process.returncode
        return CommandResult(
            exit_code=None if timed_out or code is None or code < 0 else code,
            output=text[:OUTPUT_MAX_CHARS],
            truncated=output.seen > len(output.kept) or len(text) > OUTPUT_MAX_CHARS,
            timed_out=timed_out,
        )


class _Output:
    """The output read so far: the first bytes kept, and how many came."""

    def __init__(self) -> None:
        self.kept = bytearray()
        self.seen = 0

    async def read(self, stream: asyncio.StreamReader) -> None:
        # Read while the command runs, so it never blocks on a full pipe.
        while chunk := await stream.read(_CHUNK):
            self.seen += len(chunk)
            self.kept += chunk[: _KEPT_BYTES - len(self.kept)]


async def _exited(process: asyncio.subprocess.Process) -> None:
    """Until the shell exits.

    Not `process.wait()`: in Python 3.14.4 it also waits for the pipes to
    close, which a child in the background keeps open (3.14.8 and 3.15 do
    not; checked on 2026-10-23). `returncode` is set as soon as the shell
    exits in all of them, and there is no public event to wait for.
    """
    while process.returncode is None:  # noqa: ASYNC110 (see above)
        await asyncio.sleep(EXIT_POLL_SECONDS)


def _become_subreaper() -> None:
    """Make the orphans of every command children of `maha` (Linux)."""
    with contextlib.suppress(OSError, AttributeError):
        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)


def _children() -> set[int]:
    """The pids whose parent is `maha`, from /proc."""
    me = os.getpid()
    found = set()
    with contextlib.suppress(OSError), os.scandir("/proc") as entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                # Bytes: the name is whatever the process chose, in any
                # encoding or none.
                with open(os.path.join(entry.path, "stat"), "rb") as file:
                    stat = file.read()
            except OSError:
                continue
            # "pid (name) state ppid …"; the name can hold spaces and ")".
            fields = stat[stat.rindex(b")") + 2 :].split()
            if int(fields[1]) == me:
                found.add(int(entry.name))
    return found


async def _kill_escaped(known: set[int]) -> None:
    """Kill and reap what is left of a command: the processes that left its
    group, now children of `maha`, and theirs as they become orphans too.
    It stops after a round that finds none."""
    for _ in range(ESCAPED_ROUNDS):
        left = _children() - known
        for pid in left:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # Of another user (`sudo … &`): not ours to kill, and left
                # alone, as `_kill_group` does.
                known.add(pid)
        known |= {pid for pid in left if _reaped(pid)}
        if not left:
            return
        await asyncio.sleep(ESCAPED_PAUSE)


def _reaped(pid: int) -> bool:
    """Reap a killed orphan, without waiting: a zombie left unreaped would
    stay in the process table. False if it has not died yet."""
    try:
        return os.waitpid(pid, os.WNOHANG)[0] != 0
    except ChildProcessError:
        # Not ours any more, or already reaped.
        return True


def _kill_group(pid: int) -> None:
    # The group may be gone already.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)
