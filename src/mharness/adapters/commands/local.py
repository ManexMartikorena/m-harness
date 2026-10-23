"""Shell commands on this machine (spec hito 5, §1.9).

Each command runs in its own process group: Ctrl+C in the terminal does not
reach it, and `maha` kills the whole group, grandchildren included, when the
time is up, when the task is cancelled, and when its shell ends. No
threads: the output is read with asyncio while the command runs, so a
command that writes a lot never blocks on a full pipe.

It runs with your permissions and no sandbox until hito 14: the defence is
that you read the command before approving it.
"""

import asyncio
import contextlib
import os
import signal
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


class LocalCommandRunner:
    async def run(
        self, command: str, *, cwd: Path, time_limit: float, env: Mapping[str, str]
    ) -> CommandResult:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            env=dict(env),
            # A command that asks for input does not wait for it.
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            process_group=0,
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


def _kill_group(pid: int) -> None:
    # The group may be gone already.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)
