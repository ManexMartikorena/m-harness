"""The project on the local disk (spec hito 10, §1.4 and §1.7).

The git root is found by looking for `.git` (a directory, or a file in a
worktree or a submodule) from the working directory up: no `git` runs.

The project's instruction files never leave the git root (or the working
directory, without git) and are never secrets: a cloned repository chooses
what they say, but not what of the user's they send to the provider.
"""

import asyncio
import os
import stat
import sys
from collections.abc import Callable, Iterator, Sequence
from datetime import date
from pathlib import Path, PurePath

from mharness.domain.paths import SKIPPED_DIRS, is_inside, is_secret_at, printable
from mharness.domain.prompt import (
    INSTRUCTIONS_MAX,
    Environment,
    Instructions,
    Layer,
    LayerKind,
)
from mharness.domain.wildcard import glob_matches

AGENTS = "AGENTS.md"
# Read where there is no AGENTS.md, in this order (§1.4).
CLAUDE = ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md")
# Entries a glob of `instructions` may look at: a pattern of a project's
# file must not keep maha from starting (§1.5).
GLOB_MAX_SCAN = 10_000
_MAGIC = frozenset("*?[")


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


class _Unread(Exception):
    """A file that is not read, and why, for the user."""


def _read(path: Path, *, inside: Path | None) -> str | None:
    """The text of an instruction file, None if there is none, or
    `_Unread`. With `inside`, the file (also through a link) has to be in
    that directory and not a secret. At most `INSTRUCTIONS_MAX` bytes are
    read: a bigger file keeps the mark of what is left."""
    try:
        if not path.is_file() and not path.is_symlink():
            return None
        real = path.resolve(strict=True)
    except FileNotFoundError:
        # A broken link: as if there were no file.
        return None
    except (OSError, RuntimeError) as exc:
        raise _Unread("cannot be read") from exc
    if inside is not None:
        if not is_inside(real, inside):
            raise _Unread("a link out of the project, not read")
        if is_secret_at(real, inside):
            raise _Unread("a secret file, not read")
    try:
        # Without blocking: a link to a FIFO must not stop maha.
        fd = os.open(real, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError as exc:
        raise _Unread("cannot be read") from exc
    with os.fdopen(fd, "rb") as file:
        try:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise _Unread("not a regular file, not read")
            data = file.read(INSTRUCTIONS_MAX)
        except OSError as exc:
            raise _Unread("cannot be read") from exc
    cut = len(data) < info.st_size
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Only a character cut by the limit, at the very end, is fine.
        if not (cut and exc.reason == "unexpected end of data"):
            raise _Unread("not UTF-8, not read") from None
        text = data[: exc.start].decode("utf-8")
    if cut:
        more = info.st_size - len(text.encode("utf-8"))
        return f"{text.rstrip()}\n[truncated: {more} bytes more]"
    return text.strip() or None


class LocalProject:
    """A `ProjectInfo` over the directory where `maha` runs.

    `shell` is the one commands run in (`/bin/sh` for `run_command`), or
    None when there is no tool to run them; `today` gives the date, local.
    The user's instructions are in `config_dir` (`~/.config/maha`), or
    without them, with `compat_claude`, in `~/.claude/CLAUDE.md`; `user`
    False leaves them out (the evals measure maha, not the user's habits).
    The extra `instructions` of the user's configuration and of the
    project's are paths or globs from the working directory; the
    project's never leave the project (§1.5).
    """

    def __init__(
        self,
        cwd: Path,
        *,
        shell: str | None,
        home: Path,
        config_dir: Path,
        compat_claude: bool = True,
        user: bool = True,
        extra_user: Sequence[str] = (),
        extra_project: Sequence[str] = (),
        today: Callable[[], date] = date.today,
        platform: str = sys.platform,
    ) -> None:
        self._cwd = cwd
        self._shell = shell
        self._home = home
        self._config_dir = config_dir
        self._compat_claude = compat_claude
        self._user = user
        self._extra_user = tuple(extra_user)
        self._extra_project = tuple(extra_project)
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

    async def instructions(self) -> Instructions:
        return await asyncio.to_thread(self._instructions)

    def _instructions(self) -> Instructions:
        layers: list[Layer] = []
        warnings: list[str] = []

        # Each file once, also when a glob names an AGENTS.md again.
        seen: set[Path] = set()

        def add(kind: LayerKind, path: Path, inside: Path | None) -> bool:
            source = self._shown(path)
            try:
                real = path.resolve()
            except OSError, RuntimeError:
                real = path
            if real in seen:
                return True
            try:
                text = _read(path, inside=inside)
            except _Unread as why:
                warnings.append(f"{source}: {why}")
                return True
            if text is None:
                return False
            seen.add(real)
            layers.append(Layer(kind=kind, source=source, text=text))
            return True

        if self._user:
            mine = self._config_dir / AGENTS
            if not add("user", mine, None) and self._compat_claude:
                add("user", self._home / ".claude" / "CLAUDE.md", None)
        root = git_root(self._cwd) or self._cwd
        for directory in _down(root, self._cwd):
            if add("project", directory / AGENTS, root) or not self._compat_claude:
                continue
            for name in CLAUDE:
                add("project", directory / name, root)
        for patterns, inside in (
            (self._extra_user, None),
            (self._extra_project, root),
        ):
            for pattern in patterns:
                paths, problem = self._expand(pattern, inside)
                if problem is not None:
                    warnings.append(f"instructions {printable(pattern)!r}: {problem}")
                for path in paths:
                    if is_secret_at(path, self._cwd):
                        warnings.append(f"{self._shown(path)}: a secret file, not read")
                    elif not add("extra", path, inside):
                        warnings.append(
                            f"instructions {printable(pattern)!r}: matches no file"
                        )
        return Instructions(layers=tuple(layers), warnings=tuple(warnings))

    def _expand(
        self, pattern: str, inside: Path | None
    ) -> tuple[list[Path], str | None]:
        """The files `pattern` names, sorted, and a problem to tell, if any.
        A path without wildcards is itself; a glob walks from its part
        without wildcards, at most `GLOB_MAX_SCAN` entries."""
        if pattern.startswith("~/") and inside is None:
            base, pattern = self._home, pattern[2:]
        else:
            base = self._cwd
        parts = PurePath(pattern).parts
        fixed = 0
        while fixed < len(parts) and not _MAGIC & set(parts[fixed]):
            fixed += 1
        if fixed == len(parts):
            return [base / pattern], None
        start = base.joinpath(*parts[:fixed])
        found: list[Path] = []
        scanned = 0
        for directory, names, files in os.walk(start):
            names[:] = sorted(name for name in names if name not in SKIPPED_DIRS)
            scanned += len(names) + len(files)
            if scanned > GLOB_MAX_SCAN:
                return sorted(found), f"stopped after {GLOB_MAX_SCAN} entries"
            here = Path(directory)
            for name in sorted(files):
                path = here / name
                if glob_matches(pattern, path.relative_to(base)):
                    found.append(path)
        if not found:
            return [], "matches no file"
        return sorted(found), None

    def _shown(self, path: Path) -> str:
        """The path as the user reads it: relative to the working
        directory if it is in it or above it, with `~` under the home."""
        if path.is_relative_to(self._cwd):
            return printable(str(path.relative_to(self._cwd)))
        root = git_root(self._cwd)
        if root is not None and path.is_relative_to(root):
            return printable(os.path.relpath(path, self._cwd))
        if path.is_relative_to(self._home):
            return printable(f"~/{path.relative_to(self._home)}")
        return printable(str(path))


def _down(root: Path, cwd: Path) -> Iterator[Path]:
    """The directories from `root` down to `cwd`, both included."""
    parts = cwd.relative_to(root).parts
    directory = root
    yield directory
    for part in parts:
        directory = directory / part
        yield directory
