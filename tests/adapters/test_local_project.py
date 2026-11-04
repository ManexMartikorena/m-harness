"""`LocalProject`: the environment and the instructions of the project, on
the disk (spec hito 10, §1.4 to §1.7)."""

from datetime import date
from pathlib import Path

from mharness.adapters.project import LocalProject
from mharness.adapters.project.local import git_root
from mharness.ports.project import ProjectInfo

TODAY = date(2026, 11, 4)


def project(cwd: Path, *, shell: str | None = "/bin/sh") -> LocalProject:
    return LocalProject(cwd, shell=shell, today=lambda: TODAY, platform="linux")


def test_it_is_a_project_info(tmp_path: Path) -> None:
    info: ProjectInfo = project(tmp_path)
    assert info is not None


async def test_the_environment_of_a_git_repository(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    cwd = tmp_path / "src" / "app"
    cwd.mkdir(parents=True)

    env = await project(cwd).environment()

    assert env.cwd == str(cwd)
    assert env.git_root == str(tmp_path)
    assert env.platform == "linux"
    assert env.shell == "/bin/sh"
    assert env.today == TODAY


async def test_without_git_or_shell(tmp_path: Path) -> None:
    env = await project(tmp_path, shell=None).environment()

    # tmp_path lives in the system's temporary directory, outside any repo.
    assert env.git_root is None
    assert env.shell is None


def test_a_git_file_is_a_root_too(tmp_path: Path) -> None:
    # A worktree or a submodule has a `.git` file that points elsewhere.
    (tmp_path / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()

    assert git_root(tmp_path / "sub") == tmp_path


def test_the_nearest_root_wins(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    inner = tmp_path / "vendor" / "lib"
    (inner / ".git").mkdir(parents=True)

    assert git_root(inner) == inner
