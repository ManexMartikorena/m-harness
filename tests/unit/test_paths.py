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
    printable,
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
        # Known credential files that were missing (spec
        # mejora-2026-10-26-deuda-pre-hito-6, A5).
        "id_ecdsa",
        "keys/id_dsa",
        "certs/client.p12",
        "certs/client.PFX",
        "prod.env",
        "deploy/app.env",
        ".envrc",
        ".npmrc",
        "web/.npmrc",
        ".pypirc",
        ".vault-token",
        ".terraformrc",
        ".terraform.d/credentials.tfrc.json",
        ".azure/accessTokens.json",
        ".config/gh/hosts.yml",
        ".config/gcloud/application_default_credentials.json",
        ".cargo/credentials.toml",
        ".cargo/credentials",
        ".git/modules/sub/config",
        ".git/modules/a/b/config",
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
        "prod.env.example",
        "docs/env.md",
        ".config/nvim/init.lua",
        "gh/hosts.yml",
        ".cargo/config.toml",
        ".git/modules/sub/HEAD",
        "modules/config",
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
        # Secret too: it often exports credentials (A5).
        ("sub/.envrc", f"{SECRET_CHANGE}; {RUNS_CODE}"),
        (".GITHUB/workflows/ci.yml", RUNS_CODE),
        # More CI, hooks and editors (spec mejora-2026-10-26-deuda-pre-hito-6,
        # A6).
        (".gitlab-ci.yml", RUNS_CODE),
        (".circleci/config.yml", RUNS_CODE),
        (".forgejo/workflows/ci.yml", RUNS_CODE),
        (".gitea/workflows/ci.yml", RUNS_CODE),
        (".githooks/pre-commit", RUNS_CODE),
        (".devcontainer/devcontainer.json", RUNS_CODE),
        (".idea/workspace.xml", RUNS_CODE),
        (".claude/settings.json", RUNS_CODE),
        ("docs/gitlab-ci.md", None),
        (".maha/config.toml", MAHA_CONFIG),
        (".git/HEAD", GIT_DIR),
        ("docs/github.md", None),
        ("envrc.txt", None),
        # Run by themselves too (audit of hito 9, H3): a `.pth` runs at every
        # start of Python, maha's grep worker included.
        (".venv/lib/python3.14/site-packages/evil.pth", RUNS_CODE),
        (".venv/bin/activate", RUNS_CODE),
        ("venv/bin/python", RUNS_CODE),
        ("node_modules/left-pad/index.js", RUNS_CODE),
        (".mcp.json", RUNS_CODE),
        (".cursor/mcp.json", RUNS_CODE),
        (".zed/tasks.json", RUNS_CODE),
        (".nvim.lua", RUNS_CODE),
        (".exrc", RUNS_CODE),
        (".cargo/config.toml", RUNS_CODE),
        (".cargo/config", RUNS_CODE),
        ("sub/.CARGO/Config.toml", RUNS_CODE),
        ("lib/anything.pth", RUNS_CODE),
        ("lib/ANYTHING.PTH", RUNS_CODE),
        ("docs/config.toml", None),
        ("docs/cargo.md", None),
        ("pth.txt", None),
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
    root = PurePath("/home/ane/project")

    assert is_inside(PurePath("/home/ane/project/a.txt"), root)
    assert not is_inside(PurePath("/home/ane/projectx/a.txt"), root)


@pytest.mark.parametrize(
    ("root", "name"),
    [
        ("/home/ane/.aws", "credentials"),
        ("/home/ane/.ssh", "config"),
        ("/home/ane/.ssh/project", "a.txt"),
        ("/home/ane/.config/gcloud", "credentials.db"),
    ],
)
def test_a_working_directory_inside_a_secret_folder_keeps_it_secret(
    root: str, name: str
) -> None:
    # Audit of hito 9, H5: only the path below the root counted, so the
    # credentials of ~/.aws were read without asking from inside it.
    where = PurePath(root)

    assert is_secret_at(where / name, where)
    assert read_warning(where / name, where, secret=SECRET_FILE) == SECRET_FILE


def test_the_asked_path_counts_too() -> None:
    # A `.env` that links to a plain name, or a plain name inside a linked
    # `.github` (spec mejora-2026-10-26-deuda-pre-hito-6, A1).
    resolved = ROOT / "config/app.txt"

    assert read_warning(resolved, ROOT, secret=SECRET_FILE) is None
    assert (
        read_warning(resolved, ROOT, secret=SECRET_FILE, asked=ROOT / ".env")
        == SECRET_FILE
    )
    assert change_warning(resolved, ROOT, asked=ROOT / ".env") == SECRET_CHANGE
    assert (
        change_warning(resolved, ROOT, asked=ROOT / ".github/workflows/ci.yml")
        == RUNS_CODE
    )


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("notas.txt", "notas.txt"),
        ("café.txt", "café.txt"),
        # A byte that is not UTF-8, as os gives it: a surrogate.
        ("caf\udce9.txt", "caf\\xe9.txt"),
        # A lone surrogate of no byte.
        ("a\ud800b", "a\\ud800b"),
    ],
)
def test_printable_names_can_go_to_json_in_utf_8(name: str, shown: str) -> None:
    assert printable(name) == shown
    printable(name).encode("utf-8")


def test_a_pth_outside_warns_that_it_runs_code() -> None:
    # The user's site-packages, outside the working directory.
    path = PurePath("/home/ane/.local/lib/python3.14/site-packages/x.pth")

    assert change_warning(path, ROOT) == f"{OUTSIDE}; {RUNS_CODE}"
