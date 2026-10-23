"""The variables a shell command gets (spec mejora-2026-10-23-deuda-hito-5,
B4 and E1).

A list of allowed names, not the environment minus the known secrets: a
credential with an unexpected name (`MI_CLAVE`) would reach the command,
and from its output, the model. `SSH_AUTH_SOCK` stays out too: it gives the
command your SSH keys.
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
# Never, even under an allowed prefix (compared without case).
CREDENTIAL_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")


def command_env(
    environ: Mapping[str, str], *, drop: Iterable[str] = ()
) -> dict[str, str]:
    """The variables of `environ` a command may see; `drop` names more that
    it may not, as the variable of the provider's key."""
    dropped = frozenset(drop)
    return {
        name: value
        for name, value in environ.items()
        if (name in ALLOWED or name.startswith(ALLOWED_PREFIXES))
        and name not in dropped
        and not name.upper().endswith(CREDENTIAL_SUFFIXES)
    }
