"""M-Harness: a general-purpose terminal agent, built from scratch."""

import os
from importlib.metadata import version


def _fill_closed_descriptors() -> None:
    """Give /dev/null to a closed stdin, stdout or stderr, before anything
    opens a file. Otherwise the first file opened takes its number: with
    `maha -p <&-`, libffi's copy of the Python binary (from `import ctypes`)
    or maha.log was read as the piped input (audit of hito 8)."""
    for fd in (0, 1, 2):
        try:
            os.fstat(fd)
        except OSError:
            # The lowest free number: this one, as the lower ones are open.
            opened = os.open(os.devnull, os.O_RDWR)
            if opened != fd:
                os.dup2(opened, fd)
                os.close(opened)


_fill_closed_descriptors()

# The distribution name, in pyproject.toml; the command is `maha`.
DISTRIBUTION = "m-harness"
__version__ = version(DISTRIBUTION)
