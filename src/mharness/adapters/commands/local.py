"""Shell commands on this machine (spec hito 5, §1.9).

Each command runs in its own process group: Ctrl+C in the terminal does not
reach it, and `maha` kills the whole group, grandchildren included, when the
time is up, when the task is cancelled, and when the command ends. No
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

from mharness.domain.commands import CommandResult

OUTPUT_MAX_CHARS = 30_000
# Enough bytes for that many characters in UTF-8; the rest is read and
# thrown away.
_KEPT_BYTES = 4 * OUTPUT_MAX_CHARS
_CHUNK = 64 * 1024


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
        kept = bytearray()
        seen = 0
        timed_out = False
        try:
            try:
                async with asyncio.timeout(time_limit):
                    while chunk := await process.stdout.read(_CHUNK):
                        seen += len(chunk)
                        kept += chunk[: _KEPT_BYTES - len(kept)]
                    await process.wait()
            except TimeoutError:
                timed_out = True
        finally:
            _kill_group(process.pid)
            # Reaped also when cancelled: SIGKILL ends it at once.
            await process.wait()
        text = kept.decode("utf-8", errors="replace")
        code = process.returncode
        return CommandResult(
            exit_code=None if timed_out or code is None or code < 0 else code,
            output=text[:OUTPUT_MAX_CHARS],
            truncated=seen > len(kept) or len(text) > OUTPUT_MAX_CHARS,
            timed_out=timed_out,
        )


def _kill_group(pid: int) -> None:
    # The group may be gone already.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)
