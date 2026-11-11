"""`LocalProject`: the environment and the instructions of the project, on
the disk (spec hito 10, §1.4 to §1.7)."""

import os
from datetime import date
from pathlib import Path

import pytest

from mharness.adapters.project import LocalProject
from mharness.adapters.project.local import git_root
from mharness.domain.prompt import INSTRUCTIONS_MAX, cap
from mharness.ports.project import ProjectInfo

TODAY = date(2026, 11, 4)


def project(
    cwd: Path,
    *,
    shell: str | None = "/bin/sh",
    home: Path | None = None,
    compat_claude: bool = True,
    user: bool = True,
) -> LocalProject:
    home = home or cwd.parent / "home"
    return LocalProject(
        cwd,
        shell=shell,
        home=home,
        config_dir=home / ".config" / "maha",
        compat_claude=compat_claude,
        user=user,
        today=lambda: TODAY,
        platform="linux",
    )


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def repo(tmp_path: Path) -> Path:
    """A git repository with a working directory two levels down."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    cwd = root / "pkg" / "app"
    cwd.mkdir(parents=True)
    return cwd


async def found(info: LocalProject) -> list[tuple[str, str, str]]:
    result = await info.instructions()
    return [(layer.kind, layer.source, layer.text) for layer in result.layers]


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


# Instructions of the project and the user (§1.4).


async def test_from_the_git_root_down(tmp_path: Path) -> None:
    cwd = repo(tmp_path)
    root = cwd.parent.parent
    write(root / "AGENTS.md", "root")
    write(root / "pkg" / "AGENTS.md", "pkg")
    write(cwd / "AGENTS.md", "app")
    # Outside the repository: never read.
    write(tmp_path / "AGENTS.md", "outside")

    assert await found(project(cwd)) == [
        ("project", "../../AGENTS.md", "root"),
        ("project", "../AGENTS.md", "pkg"),
        ("project", "AGENTS.md", "app"),
    ]


async def test_without_git_only_the_working_directory(tmp_path: Path) -> None:
    cwd = tmp_path / "a" / "b"
    write(tmp_path / "a" / "AGENTS.md", "above")
    write(cwd / "AGENTS.md", "here")

    assert await found(project(cwd)) == [("project", "AGENTS.md", "here")]


async def test_agents_md_wins_over_claude_md_in_its_directory(tmp_path: Path) -> None:
    cwd = repo(tmp_path)
    root = cwd.parent.parent
    write(root / "CLAUDE.md", "root claude")
    write(cwd / "AGENTS.md", "app agents")
    write(cwd / "CLAUDE.md", "app claude")

    assert await found(project(cwd)) == [
        ("project", "../../CLAUDE.md", "root claude"),
        ("project", "AGENTS.md", "app agents"),
    ]


async def test_the_files_of_claude_in_their_order(tmp_path: Path) -> None:
    write(tmp_path / "CLAUDE.local.md", "local")
    write(tmp_path / ".claude" / "CLAUDE.md", "dot")
    write(tmp_path / "CLAUDE.md", "main")

    assert [text for _, _, text in await found(project(tmp_path))] == [
        "main",
        "dot",
        "local",
    ]


async def test_compat_claude_off_reads_only_agents_md(tmp_path: Path) -> None:
    write(tmp_path / "CLAUDE.md", "claude")
    home = tmp_path / "home"
    write(home / ".claude" / "CLAUDE.md", "mine")

    assert await found(project(tmp_path, home=home, compat_claude=False)) == []


async def test_the_users_file_goes_first(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write(home / ".config" / "maha" / "AGENTS.md", "mine")
    write(home / ".claude" / "CLAUDE.md", "claude")
    cwd = tmp_path / "work"
    write(cwd / "AGENTS.md", "project")

    assert await found(project(cwd, home=home)) == [
        ("user", "~/.config/maha/AGENTS.md", "mine"),
        ("project", "AGENTS.md", "project"),
    ]


async def test_without_the_users_file_the_one_of_claude(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write(home / ".claude" / "CLAUDE.md", "claude")

    assert await found(project(tmp_path / "work", home=home)) == [
        ("user", "~/.claude/CLAUDE.md", "claude")
    ]


async def test_the_evals_leave_the_user_out(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write(home / ".config" / "maha" / "AGENTS.md", "mine")

    assert await found(project(tmp_path / "work", home=home, user=False)) == []


async def test_a_link_out_of_the_project_is_not_read(tmp_path: Path) -> None:
    cwd = repo(tmp_path)
    secret = write(tmp_path / "elsewhere.md", "the user's")
    (cwd / "AGENTS.md").symlink_to(secret)

    result = await project(cwd).instructions()

    assert result.layers == ()
    assert result.warnings == ("AGENTS.md: a link out of the project, not read",)


async def test_a_link_to_a_secret_is_not_read(tmp_path: Path) -> None:
    cwd = repo(tmp_path)
    key = write(cwd / ".env", "API_KEY=x")
    (cwd / "AGENTS.md").symlink_to(key)

    result = await project(cwd).instructions()

    assert result.layers == ()
    assert result.warnings == ("AGENTS.md: a secret file, not read",)


async def test_a_link_inside_the_project_is_read(tmp_path: Path) -> None:
    cwd = repo(tmp_path)
    write(cwd / "docs" / "agents.md", "shared")
    (cwd / "AGENTS.md").symlink_to(cwd / "docs" / "agents.md")

    assert await found(project(cwd)) == [("project", "AGENTS.md", "shared")]


async def test_a_file_that_is_not_utf8_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_bytes(b"caf\xe9")

    result = await project(tmp_path).instructions()

    assert result.layers == ()
    assert result.warnings == ("AGENTS.md: not UTF-8, not read",)


async def test_a_link_to_a_fifo_does_not_block(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / "AGENTS.md").symlink_to(tmp_path / "pipe")

    result = await project(tmp_path).instructions()

    assert result.warnings == ("AGENTS.md: not a regular file, not read",)


async def test_a_broken_link_or_an_empty_file_is_no_file(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").symlink_to(tmp_path / "missing.md")
    write(tmp_path / "CLAUDE.md", "  \n")

    result = await project(tmp_path).instructions()

    assert result == type(result)()


@pytest.mark.parametrize("tail", ["", "ñ"])
async def test_a_big_file_is_read_only_up_to_the_limit(
    tmp_path: Path, tail: str
) -> None:
    # One byte and one character past the limit: what says the same as a
    # huge file, without writing one (AGENTS.md, tests of exhaustion).
    text = "a" * (INSTRUCTIONS_MAX - 1) + "ñ" + tail
    write(tmp_path / "AGENTS.md", text)

    [layer] = (await project(tmp_path).instructions()).layers

    # Read up to the limit; the mark is cap()'s, with the size on disk.
    assert layer.text == "a" * (INSTRUCTIONS_MAX - 1)
    assert layer.size == len(text.encode("utf-8"))


async def test_a_big_file_is_marked_once_with_what_was_left(tmp_path: Path) -> None:
    # Audit after hito 10 (M2): read with its mark, it passed the limit
    # again, and cap() cut it once more: "30 bytes more" of 34,464.
    big = INSTRUCTIONS_MAX + 500
    write(tmp_path / "AGENTS.md", "a" * big)

    [layer] = (await project(tmp_path).instructions()).layers
    [kept], [warning] = cap([layer])

    assert kept.text == "a" * INSTRUCTIONS_MAX + "\n[truncated: 500 bytes more]"
    assert warning.endswith("(500 bytes more)")


async def test_a_big_file_that_is_not_utf8_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_bytes(b"\xff" + b"a" * INSTRUCTIONS_MAX)

    result = await project(tmp_path).instructions()

    assert result.warnings == ("AGENTS.md: not UTF-8, not read",)


# Extra instructions of the configuration (§1.5).


async def test_extra_files_and_globs(tmp_path: Path) -> None:
    cwd = repo(tmp_path)
    write(cwd / "CONTRIBUTING.md", "contribute")
    write(cwd / "docs" / "b.md", "b")
    write(cwd / "docs" / "a.md", "a")
    write(cwd / "docs" / "c.txt", "not this")
    home = tmp_path / "home"
    write(home / "notas" / "estilo.md", "mine")

    info = LocalProject(
        cwd,
        shell=None,
        home=home,
        config_dir=home / ".config" / "maha",
        extra_user=["~/notas/estilo.md"],
        extra_project=["CONTRIBUTING.md", "docs/*.md"],
    )

    assert await found(info) == [
        ("extra", "~/notas/estilo.md", "mine"),
        ("extra", "CONTRIBUTING.md", "contribute"),
        ("extra", "docs/a.md", "a"),
        ("extra", "docs/b.md", "b"),
    ]


async def test_an_absolute_glob_of_the_user_is_read(tmp_path: Path) -> None:
    # Audit after hito 10 (M1): `relative_to` the working directory raised
    # ValueError, and maha fell at start.
    cwd = repo(tmp_path)
    notes = tmp_path / "notas"
    write(notes / "estilo.md", "mine")
    write(notes / "otra" / "mas.md", "more")
    home = tmp_path / "home"

    info = LocalProject(
        cwd,
        shell=None,
        home=home,
        config_dir=home / ".config" / "maha",
        extra_user=[f"{notes}/*.md", f"{notes}/**/*.md"],
    )

    assert [text for _, _, text in await found(info)] == ["mine", "more"]


async def test_a_file_already_loaded_is_not_repeated(tmp_path: Path) -> None:
    write(tmp_path / "AGENTS.md", "once")
    info = LocalProject(
        tmp_path,
        shell=None,
        home=tmp_path / "home",
        config_dir=tmp_path / "home" / ".config" / "maha",
        extra_project=["*.md"],
    )

    assert await found(info) == [("project", "AGENTS.md", "once")]


async def test_a_glob_skips_secrets_and_says_what_matched_nothing(
    tmp_path: Path,
) -> None:
    write(tmp_path / "notes" / ".env", "API_KEY=x")
    info = LocalProject(
        tmp_path,
        shell=None,
        home=tmp_path / "home",
        config_dir=tmp_path / "home" / ".config" / "maha",
        extra_project=["notes/*", "missing.md", "none/*.md"],
    )

    result = await info.instructions()

    assert result.layers == ()
    assert result.warnings == (
        "notes/.env: a secret file, not read",
        "instructions 'missing.md': matches no file",
        "instructions 'none/*.md': matches no file",
    )


async def test_a_glob_of_the_project_never_leaves_it(tmp_path: Path) -> None:
    cwd = repo(tmp_path)
    write(tmp_path / "outside.md", "the user's")
    (cwd / "docs").mkdir()
    (cwd / "docs" / "link.md").symlink_to(tmp_path / "outside.md")
    info = LocalProject(
        cwd,
        shell=None,
        home=tmp_path / "home",
        config_dir=tmp_path / "home" / ".config" / "maha",
        extra_project=["docs/*.md"],
    )

    result = await info.instructions()

    assert result.layers == ()
    assert result.warnings == ("docs/link.md: a link out of the project, not read",)


async def test_a_glob_stops_at_its_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A small limit says the same as a huge tree (AGENTS.md).
    monkeypatch.setattr("mharness.adapters.project.local.GLOB_MAX_SCAN", 5)
    for index in range(10):
        write(tmp_path / f"{index}.md", "x")
    info = LocalProject(
        tmp_path,
        shell=None,
        home=tmp_path / "home",
        config_dir=tmp_path / "home" / ".config" / "maha",
        extra_project=["**/*.md"],
    )

    result = await info.instructions()

    assert result.warnings == ("instructions '**/*.md': stopped after 5 entries",)


async def test_the_projects_instructions_go_from_the_folder_of_its_file(
    tmp_path: Path,
) -> None:
    # Review of the audit after hito 10 (P7): a .maha/config.toml found at
    # the root, from pkg/app, looked for its patterns in pkg/app.
    cwd = repo(tmp_path)
    root = tmp_path / "repo"
    write(root / "docs" / "CONV.md", "conventions")
    home = tmp_path / "home"

    info = LocalProject(
        cwd,
        shell=None,
        home=home,
        config_dir=home / ".config" / "maha",
        extra_project=["docs/CONV.md"],
        project_base=root,
    )

    layers = await found(info)
    assert "conventions" in [text for _, _, text in layers]
