from pathlib import PurePath

import pytest

from mharness.domain.paths import (
    GIT_DIR,
    MAHA_CONFIG,
    OUTSIDE,
    RUNS_CODE,
    SECRET_CHANGE,
    SECRET_DIR,
    SECRET_FILE,
    change_warning,
    is_inside,
    is_secret,
    is_secret_at,
    read_warning,
)


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "a/.env",
        "x.pem",
        "certs/server.key",
        "id_rsa",
        "id_ed25519.pub",
        ".netrc",
        ".ssh",
        ".ssh/config",
        ".aws/credentials",
        "home/.kube/config",
        # A file system that ignores case (/mnt/c in WSL, macOS) opens the
        # same file (spec mejora-2026-10-23-deuda-hito-5, A6).
        ".ENV",
        ".Env.Local",
        "ID_RSA",
        "X.PEM",
        ".SSH/config",
        # Remote URLs with a token, and git's stored passwords (E3).
        ".git/config",
        "repo/.git/config",
        ".GIT/CONFIG",
        ".git-credentials",
    ],
)
def test_secret_paths(path: str) -> None:
    assert is_secret(PurePath(path))


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        ".ENV.EXAMPLE",
        "env.py",
        "docs/key.md",
        "src/environment.py",
        "notas.txt",
        ".",
        ".git/HEAD",
        "src/config",
    ],
)
def test_ordinary_paths(path: str) -> None:
    assert not is_secret(PurePath(path))


# The rules about what needs a question, on resolved paths and without the
# disk (spec mejora-2026-10-23-deuda-hito-5, B1).

ROOT = PurePath("/home/ane/project")


@pytest.mark.parametrize(
    ("path", "secret", "warning"),
    [
        ("/home/ane/project/src/app.py", SECRET_FILE, None),
        ("/home/ane/project/.env", SECRET_FILE, SECRET_FILE),
        ("/home/ane/project/.env", None, None),
        ("/home/ane/notes.txt", SECRET_FILE, OUTSIDE),
        ("/home/ane/.ssh", SECRET_DIR, f"{OUTSIDE}; {SECRET_DIR}"),
        # Outside, by the absolute path: an approved ~/.ssh is still secret.
        ("/home/ane/.ssh/config", SECRET_FILE, f"{OUTSIDE}; {SECRET_FILE}"),
    ],
)
def test_read_warning(path: str, secret: str | None, warning: str | None) -> None:
    assert read_warning(PurePath(path), ROOT, secret=secret) == warning


@pytest.mark.parametrize(
    ("path", "warning"),
    [
        ("/home/ane/project/src/app.py", None),
        ("/home/ane/project/.git/hooks/pre-commit", GIT_DIR),
        ("/home/ane/project/.env", SECRET_CHANGE),
        ("/home/ane/other/.git/config", f"{OUTSIDE}; {SECRET_CHANGE}; {GIT_DIR}"),
    ],
)
def test_change_warning(path: str, warning: str | None) -> None:
    assert change_warning(PurePath(path), ROOT) == warning


@pytest.mark.parametrize(
    ("path", "warning"),
    [
        # D13: what can run code by itself, like .git.
        (".github/workflows/ci.yml", RUNS_CODE),
        (".husky/pre-commit", RUNS_CODE),
        (".vscode/tasks.json", RUNS_CODE),
        (".pre-commit-config.yaml", RUNS_CODE),
        ("sub/.envrc", RUNS_CODE),
        (".GITHUB/workflows/ci.yml", RUNS_CODE),
        (".maha/config.toml", MAHA_CONFIG),
        (".git/HEAD", GIT_DIR),
        ("docs/github.md", None),
        ("envrc.txt", None),
    ],
)
def test_change_warning_of_what_runs_code(path: str, warning: str | None) -> None:
    assert change_warning(ROOT / path, ROOT) == warning


def test_a_working_directory_inside_git_does_not_warn_every_write() -> None:
    # Only the path inside the working directory counts (it was a limit of
    # fix 6 of PR 2).
    root = PurePath("/home/ane/.git/worktree")

    assert change_warning(root / "src/app.py", root) is None


def test_inside_by_the_relative_path() -> None:
    # ".ssh" above the root is not part of the relative path.
    root = PurePath("/home/ane/.ssh/project")

    assert is_inside(PurePath("/home/ane/.ssh/project/a.txt"), root)
    assert not is_secret_at(PurePath("/home/ane/.ssh/project/a.txt"), root)
    assert is_secret_at(PurePath("/home/ane/.ssh/a.txt"), root)
