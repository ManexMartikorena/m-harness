"""The variables a shell command gets (spec mejora-2026-10-23-deuda-hito-5,
B4 and E1).

A list of allowed names, not the environment minus the known secrets: a
credential with an unexpected name (`MI_CLAVE`) would reach the command,
and from its output, the model. `SSH_AUTH_SOCK` stays out too: it gives the
command your SSH keys, and so does `XDG_RUNTIME_DIR`: its `bus` is the
session bus, with the keyring and maybe an SSH or GPG agent (audit after
hito 10, H8).

No editor opens: a command has no terminal, so an editor fails with its
screen codes in the output, or waits for a window (`code --wait`).
"""

from collections.abc import Iterable, Mapping

ALLOWED = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LANGUAGE",
        "TERM",
        "COLORTERM",
        "NO_COLOR",
        "TZ",
        "TMPDIR",
        "PWD",
        "VIRTUAL_ENV",
    }
)
ALLOWED_PREFIXES = ("LC_", "XDG_")
# Never, even under an allowed prefix.
DENIED = frozenset({"XDG_RUNTIME_DIR"})
# `true` ends at once leaving the text empty, and git stops with a clear
# error. GIT_EDITOR goes before core.editor, VISUAL and EDITOR (git-var(1),
# git 2.53, checked on 2026-10-27).
NO_EDITOR = {"GIT_EDITOR": "true", "VISUAL": "true", "EDITOR": "true"}
# Never, even under an allowed prefix (compared without case).
CREDENTIAL_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")


def is_credential(name: str) -> bool:
    """Whether a variable is named as a credential (compared without case)."""
    return name.upper().endswith(CREDENTIAL_SUFFIXES)


def command_env(
    environ: Mapping[str, str],
    *,
    drop: Iterable[str] = (),
    extra: Iterable[str] = (),
) -> dict[str, str]:
    """The variables of `environ` a command may see; `drop` names more that
    it may not, as the variable of the provider's key, and `extra` more that
    it may, chosen by the user (audit after hito 10, P5). A credential never
    passes. The editor is always `NO_EDITOR`'s."""
    dropped = frozenset(drop)
    added = frozenset(extra)
    allowed = {
        name: value
        for name, value in environ.items()
        if (
            name in added
            or (
                (name in ALLOWED or name.startswith(ALLOWED_PREFIXES))
                and name not in DENIED
            )
        )
        and name not in dropped
        and not is_credential(name)
    }
    return {**allowed, **NO_EDITOR}
