"""A saved conversation and what its file holds (DESIGN §5, spec hito 6,
§1.2).

A session file is a header and then entries, one per line, only ever
appended: the messages of each turn, the tokens it used, and the model
changes. Reading it back gives a `Session`.
"""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from mharness.domain.messages import Message
from mharness.domain.model import Usage

# Date and time in UTC, and 4 random hex digits: short to type, sorted by
# date, and two sessions in the same second do not clash.
_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")


def session_id(created_at: datetime, token: str) -> str:
    """The id of a session created at `created_at` (UTC), with the random
    `token` (4 hex digits)."""
    return f"{created_at:%Y%m%d-%H%M%S}-{token}"


def is_session_id(text: str) -> bool:
    """Whether `text` has the form of an id. Checked before an id becomes a
    file name: `/resume ../../etc/passwd` never reaches the disk."""
    return _ID.fullmatch(text) is not None


class SessionHeader(BaseModel, frozen=True):
    """The first line of a session file."""

    id: str
    created_at: datetime
    # The resolved directory where maha ran.
    cwd: str
    provider: str
    # The model when the session started; a `ModelEntry` changes it.
    model: str
    # The version of maha that created it.
    maha: str


class MessageEntry(BaseModel, frozen=True):
    """One message of a finished turn."""

    type: Literal["message"] = "message"
    message: Message


class UsageEntry(BaseModel, frozen=True):
    """The tokens of one finished turn, for the cost of hito 7."""

    type: Literal["usage"] = "usage"
    usage: Usage


class ModelEntry(BaseModel, frozen=True):
    """`/model` changed the model from here on."""

    type: Literal["model"] = "model"
    model: str


# Validated by `type`, as the blocks of a message.
type SessionEntry = Annotated[
    MessageEntry | UsageEntry | ModelEntry, Field(discriminator="type")
]


class Session(BaseModel, frozen=True):
    """A session read back from its file."""

    header: SessionHeader
    messages: list[Message]
    # The last one: the header's, or that of the last `ModelEntry`.
    model: str
    # The sum of every `UsageEntry`.
    usage: Usage


class SessionSummary(BaseModel, frozen=True):
    """What `/sessions` shows of a session."""

    id: str
    cwd: str
    updated_at: datetime
    messages: int
    # The first line of the first user message, cut.
    title: str


class SessionError(Exception):
    """A session cannot be used; the message says why."""


class SessionNotFound(SessionError):
    """No session with that id."""


class SessionInUse(SessionError):
    """Another maha has the session open."""


class SessionCorrupt(SessionError):
    """The file cannot be read back as a session."""
