from pathlib import PurePath

import pytest

from mharness.domain.paths import is_secret


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
