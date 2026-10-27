"""Untrusted text made safe to print (spec mejora-2026-10-23-deuda-hito-5,
A2).

Text from the model, a tool or a file can carry terminal control sequences
(ESC, `\r`…) that repaint the screen, or bidi controls that reorder it. The
screen could then lie, for example about the question just below a call.
They are shown escaped, as `\x1b` or `\u202e`.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# C0 and C1 controls but newline and tab, and the bidi embeddings,
# overrides, isolates and marks.
_UNSAFE = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)


def _escaped(match: re.Match[str]) -> str:
    code = ord(match.group())
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"


def clean(text: str) -> str:
    """`text` with every unsafe character escaped."""
    return _UNSAFE.sub(_escaped, text)


def clean_line(text: str) -> str:
    """`text` clean and on one line: its line breaks and tabs escaped too, so
    a title cannot push the start of a command off the screen."""
    return clean(text).replace("\n", "\\n").replace("\t", "\\t")


# The smallest cost shown: a hundredth of a cent.
_SMALLEST = Decimal("0.0001")


def usd(amount: Decimal) -> str:
    """$0.0008: four decimals, enough for a turn; never a "$0.0000" that
    looks free when it is not (spec hito 7, §1.5)."""
    if amount.is_zero():
        return "$0"
    try:
        shown = amount.quantize(_SMALLEST, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        # More digits than Decimal keeps: too big for four decimals.
        return f"${amount:f}"
    return f"<${_SMALLEST}" if shown.is_zero() else f"${shown}"
