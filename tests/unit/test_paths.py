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
    ],
)
def test_secret_paths(path: str) -> None:
    assert is_secret(PurePath(path))


@pytest.mark.parametrize(
    "path",
    [".env.example", "env.py", "docs/key.md", "src/environment.py", "notas.txt", "."],
)
def test_ordinary_paths(path: str) -> None:
    assert not is_secret(PurePath(path))
