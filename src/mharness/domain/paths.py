"""Rules about paths, without touching the disk (spec hito 4, §1.6).

Secret files stay away from the model (DESIGN §10): their content would end
up at the provider.
"""

from fnmatch import fnmatchcase
from pathlib import PurePath

# Everything inside these directories is secret.
SECRET_DIRS = frozenset({".ssh", ".aws", ".gnupg", ".docker", ".kube"})
SECRET_NAMES = ("*.pem", "*.key", "id_rsa*", "id_ed25519*", ".netrc", ".pgpass")
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
    if any(part in SECRET_DIRS for part in path.parts):
        return True
    name = path.name
    if name in NOT_SECRET:
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    return any(fnmatchcase(name, pattern) for pattern in SECRET_NAMES)
