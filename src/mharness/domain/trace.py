"""What a trace keeps, and the masking of credentials (DESIGN §5 and §11,
spec hito 7, §1.7 and §1.8).

A trace is one record per line: when, which session, and what happened.
Every event of the loop but the pieces of text, plus how a turn ended badly.
Before a record leaves the process, every text in it goes through `mask()`:
a trace is for auditing, and may end up shared.
"""

import re
from collections.abc import Collection, Iterable, Mapping
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from mharness.domain.agent_events import (
    ApprovalRequested,
    ModelCallFinished,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
    TurnStarted,
)

REDACTED = "[redacted]"

# A known value this short is not masked: it would hit ordinary text.
MIN_SECRET = 9

# Names of variables whose values are credentials.
_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD", re.IGNORECASE)

# Shapes of credentials with a recognizable prefix. Not every secret: one
# with another shape gets through (spec hito 7, §10).
_SHAPES = re.compile(
    "|".join(
        [
            r"sk-[A-Za-z0-9_-]{16,}",  # OpenAI, Anthropic and many more
            r"gh[pousr]_[A-Za-z0-9]{36,}",  # GitHub tokens
            r"github_pat_[A-Za-z0-9_]{22,}",  # GitHub fine-grained tokens
            r"AKIA[0-9A-Z]{16}",  # AWS access key ids
            r"xox[abposr]-[A-Za-z0-9-]{10,}",  # Slack
            r"AIza[0-9A-Za-z_-]{35}",  # Google API keys
            # PEM private keys, whole.
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        ]
    ),
    re.DOTALL,
)


class TurnFailed(BaseModel, frozen=True):
    """The turn ended with an exception: a failed call to the model, or a
    bug. There is no `AgentError` event: the trace notes it from outside
    the loop (spec hito 7, §1.6)."""

    type: Literal["error"] = "error"
    # The exception's class name.
    kind: str
    message: str


class TurnInterrupted(BaseModel, frozen=True):
    """The user cut the turn with Ctrl+C."""

    type: Literal["interrupted"] = "interrupted"


type TraceEvent = Annotated[
    TurnStarted
    | ToolCallProposed
    | ApprovalRequested
    | ToolFinished
    | ModelCallFinished
    | TurnFinished
    | TurnFailed
    | TurnInterrupted,
    Field(discriminator="type"),
]


class TraceRecord(BaseModel, frozen=True):
    """One line of a trace."""

    at: datetime
    session: str
    event: TraceEvent


def known_secrets(
    env: Mapping[str, str], *, also: Iterable[str | None] = ()
) -> set[str]:
    """The values to mask: those of the variables whose name looks like a
    credential (`*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`), and `also`
    (the provider's key). Short ones are left out."""
    values = [value for name, value in env.items() if _SECRET_NAME.search(name)]
    values += [value for value in also if value]
    return {value for value in values if len(value) >= MIN_SECRET}


def mask(text: str, known: Collection[str]) -> str:
    """`text` with every known value and every credential shape replaced by
    `[redacted]`."""
    # The longer first: a value that holds another is masked whole.
    for value in sorted(known, key=len, reverse=True):
        if len(value) >= MIN_SECRET:
            text = text.replace(value, REDACTED)
    return _SHAPES.sub(REDACTED, text)


def redact(record: TraceRecord, known: Collection[str]) -> TraceRecord:
    """The record with every text in it masked."""
    data = _masked(record.model_dump(mode="json"), known)
    return TraceRecord.model_validate(data)


def _masked(data: Any, known: Collection[str]) -> Any:
    match data:
        case str():
            return mask(data, known)
        case dict():
            return {key: _masked(value, known) for key, value in data.items()}
        case list():
            return [_masked(value, known) for value in data]
        case _:
            return data
