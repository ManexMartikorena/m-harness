"""Rules about paths, without touching the disk (spec hito 4, §1.6).

Secret files stay away from the model (DESIGN §10): their content would end
up at the provider. What needs a question before reading or changing a
path is decided here too, on paths already resolved, so every tool shares it
(spec mejora-2026-10-23-deuda-hito-5, B1).
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

    `path` is relative to the working directory, or absolute outside it
    (`is_secret_at`).
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


# The warnings of a question (spec hito 5, §1.6).
OUTSIDE = "outside the working directory"
SECRET_FILE = "secret file: its content goes to the model provider"
SECRET_DIR = "secret directory: its file names go to the model provider"
# Changing a secret: what it risks is not the model reading it (spec
# mejora-2026-10-23-deuda-hito-5, C).
SECRET_CHANGE = "secret file: it may hold credentials"
# Writing in .git always asks: a hook or the config can run code (review of
# PR 2, fix 6). Reading it does not.
GIT_DIR = "git directory: hooks and config here can run code"
# Other places whose files run by themselves: hooks, CI, editor tasks,
# direnv. Writing there always asks too (spec mejora-2026-10-23-deuda-hito-5,
# D13). All names in lower case.
RUNS_CODE = "runs code: hooks, CI or editor tasks here can run code"
CODE_DIRS = frozenset({".github", ".husky", ".vscode"})
CODE_FILES = frozenset({".pre-commit-config.yaml", ".envrc"})
MAHA_CONFIG = "maha configuration: it chooses the provider and the model"


def is_inside(path: PurePath, root: PurePath) -> bool:
    """Whether the resolved `path` is in the working directory `root`."""
    return path.is_relative_to(root)


def is_secret_at(path: PurePath, root: PurePath) -> bool:
    """`is_secret` for a resolved path. Inside, by the path relative to the
    root; outside, by the absolute path, so an approved `~/.ssh` still counts
    as secret."""
    if is_inside(path, root):
        return is_secret(path.relative_to(root))
    return is_secret(path)


def read_warning(path: PurePath, root: PurePath, *, secret: str | None) -> str | None:
    """Why reading the resolved `path` needs a question, or None. `secret` is
    the warning for a secret path, or None if secrets do not ask."""
    found = []
    if not is_inside(path, root):
        found.append(OUTSIDE)
    if secret is not None and is_secret_at(path, root):
        found.append(secret)
    return "; ".join(found) or None


def change_warning(path: PurePath, root: PurePath) -> str | None:
    """Why changing the resolved `path` cannot be approved for the whole
    session: the warnings of reading it, and what can run code.

    Inside, only the path below the root counts: a working directory inside
    a `.git` folder does not make every write warn.
    """
    found = [read_warning(path, root, secret=SECRET_CHANGE)]
    seen = path.relative_to(root) if is_inside(path, root) else path
    parts = [part.casefold() for part in seen.parts]
    if ".git" in parts:
        found.append(GIT_DIR)
    elif any(part in CODE_DIRS for part in parts) or (
        parts and parts[-1] in CODE_FILES
    ):
        found.append(RUNS_CODE)
    elif ".maha" in parts:
        found.append(MAHA_CONFIG)
    return "; ".join(warning for warning in found if warning) or None
