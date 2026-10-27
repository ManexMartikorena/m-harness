"""What a trace keeps, and the masking of credentials (DESIGN §5 and §11,
spec hito 7, §1.7 and §1.8).

A trace is one record per line: when, which session, and what happened.
Every event of the loop but the pieces of text, plus how a turn ended badly.
Before a record leaves the process, every text in it goes through `mask()`:
a trace is for auditing, and may end up shared.
"""

import json
import re
from collections.abc import Iterable, Mapping
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, Field

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
            # PEM private keys: whole, or to the end of a text cut before its
            # END line (read_file with a limit, `head id_rsa`).
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
            r"(?:.*?-----END [A-Z ]*PRIVATE KEY-----|.*\Z)",
        ]
    ),
    re.DOTALL,
)


class TraceError(Exception):
    """A trace cannot be written, read or deleted; the message says why.
    It never cuts a conversation (spec hito 7, §1.7)."""


class TraceExists(TraceError):
    """A new session's trace would take an id already in use."""


class TurnFailed(BaseModel, frozen=True):
    """The turn ended with an exception: a failed call to the model, or a
    bug. There is no `AgentError` event: the trace notes it from outside
    the loop (spec hito 7, §1.6)."""

    type: Literal["error"] = "error"
    # The exception's class name.
    kind: str
    message: str


class TurnInterrupted(BaseModel, frozen=True):
    """The turn was cut before it finished: Ctrl+C, whoever was reading it
    stopped, or a time limit."""

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

    # With its time zone: /trace orders and subtracts them.
    at: AwareDatetime
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


class Secrets:
    """The known values to mask, ready once for every text: also as they
    look escaped inside JSON text (the arguments of a call are JSON that
    the model wrote), and the longer first, so that a value holding another
    is masked whole. Short ones are left out."""

    def __init__(self, values: Iterable[str] = ()) -> None:
        forms: set[str] = set()
        for value in values:
            if len(value) < MIN_SECRET:
                continue
            for escaped in (value, _in_json(value, ascii=False), _in_json(value)):
                forms.update((escaped, escaped.replace("/", "\\/")))
        self._forms = tuple(sorted(forms, key=len, reverse=True))

    def mask(self, text: str) -> str:
        for form in self._forms:
            text = text.replace(form, REDACTED)
        return text


def mask(text: str, secrets: Secrets) -> str:
    """`text` with every known value and every credential shape replaced by
    `[redacted]`."""
    return _SHAPES.sub(REDACTED, secrets.mask(text))


def redact(record: TraceRecord, secrets: Secrets) -> TraceRecord:
    """The record with every text in it masked."""
    data = _masked(record.model_dump(mode="json"), secrets)
    return TraceRecord.model_validate(data)


def _in_json(value: str, *, ascii: bool = True) -> str:
    """How `value` looks inside a JSON string, without the quotes."""
    return json.dumps(value, ensure_ascii=ascii)[1:-1]


def _masked(data: Any, secrets: Secrets) -> Any:
    match data:
        case str():
            return mask(data, secrets)
        case dict():
            return {key: _masked(value, secrets) for key, value in data.items()}
        case list():
            return [_masked(value, secrets) for value in data]
        case _:
            return data
