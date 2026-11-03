"""Rules about paths, without touching the disk (spec hito 4, §1.6).

Secret files stay away from the model (DESIGN §10): their content would end
up at the provider. What needs a question before reading or changing a
path is decided here too, on paths already resolved, so every tool shares it
(spec mejora-2026-10-23-deuda-hito-5, B1).
"""

from fnmatch import fnmatchcase
from itertools import pairwise
from pathlib import PurePath

# Everything inside these directories is secret. All names in lower case.
SECRET_DIRS = frozenset({".ssh", ".aws", ".gnupg", ".docker", ".kube", ".azure"})
# Two directories in a row: everything inside them is secret (spec
# mejora-2026-10-26-deuda-pre-hito-6, A5).
SECRET_SUBDIRS = frozenset({(".config", "gh"), (".config", "gcloud")})
SECRET_NAMES = (
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.env",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "id_dsa*",
    ".netrc",
    ".pgpass",
    ".git-credentials",
    ".envrc",
    ".npmrc",
    ".pypirc",
    ".vault-token",
    ".terraformrc",
    "credentials.tfrc.json",
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
    parts = [part.casefold() for part in path.parts]
    if any(part in SECRET_DIRS for part in parts):
        return True
    if any(pair in SECRET_SUBDIRS for pair in pairwise(parts)):
        return True
    name = path.name.casefold()
    parent = parts[-2] if len(parts) > 1 else ""
    # Its remote URLs can carry a token (spec mejora-2026-10-23-deuda-hito-5,
    # E3), also a submodule's, kept in .git/modules (A5). The rest of .git
    # is not secret.
    if name == "config" and (
        parent == ".git" or (".git" in parts and "modules" in parts)
    ):
        return True
    # Cargo's registry tokens.
    if parent == ".cargo" and name.startswith("credentials"):
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
# D13, and mejora-2026-10-26-deuda-pre-hito-6, A6). All names in lower case.
RUNS_CODE = "runs code: hooks, CI or editor tasks here can run code"
CODE_DIRS = frozenset(
    {
        ".github",
        ".gitlab",
        ".circleci",
        ".forgejo",
        ".gitea",
        ".husky",
        ".githooks",
        ".vscode",
        ".idea",
        ".devcontainer",
        ".claude",
        # More editors and agents, and installed packages: a `.pth` in a
        # site-packages runs at every start of Python, maha's grep worker
        # included (audit of hito 9, H3).
        ".cursor",
        ".zed",
        ".venv",
        "venv",
        "node_modules",
    }
)
CODE_FILES = frozenset(
    {
        ".pre-commit-config.yaml",
        ".envrc",
        ".gitlab-ci.yml",
        ".mcp.json",
        ".nvim.lua",
        ".exrc",
    }
)
# Anywhere: Python runs the `.pth` files of its site directories.
CODE_PATTERNS = ("*.pth",)
# A file in a directory: cargo's config can set the build's commands.
CODE_SUBFILES = frozenset({(".cargo", "config"), (".cargo", "config.toml")})
MAHA_CONFIG = "maha configuration: it chooses the provider and the model"


def printable(name: str) -> str:
    """`name` as the model and the user see it, always valid UTF-8.

    A file name with bytes that are not UTF-8 comes from `os` with
    surrogates ("caf\\udce9.txt" for b"caf\\xe9.txt"): no request to a
    model can encode them, and a tool result with one would block the
    session for good (audit of hito 9, H2). Each such byte is shown as
    `\\xe9`; any other lone surrogate, as `\\ud800`.
    """
    if name.isascii():
        return name
    return "".join(_escaped(char) if _is_surrogate(char) else char for char in name)


def _is_surrogate(char: str) -> bool:
    return 0xD800 <= ord(char) <= 0xDFFF


def _escaped(char: str) -> str:
    code = ord(char)
    # `surrogateescape`: U+DC80 to U+DCFF stand for the bytes 0x80 to 0xFF.
    if 0xDC80 <= code <= 0xDCFF:
        return f"\\x{code - 0xDC00:02x}"
    return f"\\u{code:04x}"


def is_inside(path: PurePath, root: PurePath) -> bool:
    """Whether the resolved `path` is in the working directory `root`."""
    return path.is_relative_to(root)


def is_secret_at(path: PurePath, root: PurePath) -> bool:
    """`is_secret` for a resolved path, by its absolute path, so an approved
    `~/.ssh` still counts as secret, and also a working directory inside one
    (audit of hito 9, H5). Inside, by the path relative to the root too."""
    if is_inside(path, root) and is_secret(path.relative_to(root)):
        return True
    return is_secret(path)


def read_warning(
    path: PurePath,
    root: PurePath,
    *,
    secret: str | None,
    asked: PurePath | None = None,
) -> str | None:
    """Why reading the resolved `path` needs a question, or None. `secret` is
    the warning for a secret path, or None if secrets do not ask.

    `asked` is the path as the model wrote it, made absolute but not
    resolved: a `.env` that links to `config/app.txt` is still secret (spec
    mejora-2026-10-26-deuda-pre-hito-6, A1).
    """
    found = []
    if not is_inside(path, root):
        found.append(OUTSIDE)
    if secret is not None and any(
        is_secret_at(seen, root) for seen in _both(path, asked)
    ):
        found.append(secret)
    return "; ".join(found) or None


def change_warning(
    path: PurePath, root: PurePath, *, asked: PurePath | None = None
) -> str | None:
    """Why changing the resolved `path` cannot be approved for the whole
    session: the warnings of reading it, and what can run code. `asked`, as
    in `read_warning`.

    Inside, only the path below the root counts: a working directory inside
    a `.git` folder does not make every write warn.
    """
    found = [read_warning(path, root, secret=SECRET_CHANGE, asked=asked)]
    seen = [
        each.relative_to(root) if is_inside(each, root) else each
        for each in _both(path, asked)
    ]
    parts = {part.casefold() for each in seen for part in each.parts}
    names = {each.name.casefold() for each in seen}
    if ".git" in parts:
        found.append(GIT_DIR)
    elif parts & CODE_DIRS or names & CODE_FILES or _runs_code(seen):
        found.append(RUNS_CODE)
    elif ".maha" in parts:
        found.append(MAHA_CONFIG)
    return "; ".join(warning for warning in found if warning) or None


def _runs_code(seen: list[PurePath]) -> bool:
    """Whether a file of `seen` runs code by its name and its folder."""
    for each in seen:
        name = each.name.casefold()
        if any(fnmatchcase(name, pattern) for pattern in CODE_PATTERNS):
            return True
        if (each.parent.name.casefold(), name) in CODE_SUBFILES:
            return True
    return False


def _both(path: PurePath, asked: PurePath | None) -> list[PurePath]:
    """The resolved path and, if given, the asked one."""
    return [path] if asked is None else [path, asked]
