"""Rules about paths, without touching the disk (spec hito 4, §1.6).

Secret files stay away from the model (DESIGN §10): their content would end
up at the provider.
"""

from fnmatch import fnmatchcase
from pathlib import PurePath

# Everything inside these directories is secret. All names in lower case.
SECRET_DIRS = frozenset({".ssh", ".aws", ".gnupg", ".docker", ".kube"})
SECRET_NAMES = (
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    ".netrc",
    ".pgpass",
    ".git-credentials",
)
# Templates without values, kept in repositories.
NOT_SECRET = frozenset({".env.example"})

# Skipped when searching (glob, grep): version control, environments, caches.
SKIPPED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)


def is_secret(path: PurePath) -> bool:
    """True for a secret file, or a secret directory and what is inside it.

    `path` is relative to the working directory.
    """
    # Without case: a file system that ignores it opens the same file (spec
    # mejora-2026-10-23-deuda-hito-5, A6).
    if any(part.casefold() in SECRET_DIRS for part in path.parts):
        return True
    name = path.name.casefold()
    # Its remote URLs can carry a token (spec mejora-2026-10-23-deuda-hito-5,
    # E3). The rest of .git is not secret.
    if name == "config" and len(path.parts) > 1 and path.parts[-2].casefold() == ".git":
        return True
    if name in NOT_SECRET:
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    return any(fnmatchcase(name, pattern) for pattern in SECRET_NAMES)
