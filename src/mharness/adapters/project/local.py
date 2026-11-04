"""The project on the local disk (spec hito 10, §1.4 and §1.7).

The git root is found by looking for `.git` (a directory, or a file in a
worktree or a submodule) from the working directory up: no `git` runs.
"""

import asyncio
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

from mharness.domain.prompt import Environment


def git_root(cwd: Path) -> Path | None:
    """The nearest directory, `cwd` or above, that holds a `.git`."""
    for directory in (cwd, *cwd.parents):
        try:
            if (directory / ".git").exists():
                return directory
        except OSError:
            # A directory that cannot be looked at ends nothing: go on.
            continue
    return None


class LocalProject:
    """A `ProjectInfo` over the directory where `maha` runs.

    `shell` is the one commands run in (`/bin/sh` for `run_command`), or
    None when there is no tool to run them; `today` gives the date, local.
    """

    def __init__(
        self,
        cwd: Path,
        *,
        shell: str | None,
        today: Callable[[], date] = date.today,
        platform: str = sys.platform,
    ) -> None:
        self._cwd = cwd
        self._shell = shell
        self._today = today
        self._platform = platform

    async def environment(self) -> Environment:
        root = await asyncio.to_thread(git_root, self._cwd)
        return Environment(
            cwd=str(self._cwd),
            git_root=None if root is None else str(root),
            platform=self._platform,
            shell=self._shell,
            today=self._today(),
        )
