"""Untrusted text made safe to print (spec mejora-2026-10-23-deuda-hito-5,
A2).

Text from the model, a tool or a file can carry terminal control sequences
(ESC, `\r`…) that repaint the screen, or bidi controls that reorder it. The
screen could then lie, for example about the question just below a call.
They are shown escaped, as `\x1b` or `‮`.
"""

import re

# C0 and C1 controls but newline and tab, and the bidi embeddings,
# overrides, isolates and marks.
_UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f؜‎‏‪-‮⁦-⁩]")


def _escaped(match: re.Match[str]) -> str:
    code = ord(match.group())
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"


def clean(text: str) -> str:
    """`text` with every unsafe character escaped."""
    return _UNSAFE.sub(_escaped, text)
