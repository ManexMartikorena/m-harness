"""A saved conversation and what its file holds (DESIGN §5, spec hito 6,
§1.2).

A session file is a header and then entries, one per line, only ever
appended: the messages of each turn, the tokens it used, and the model
changes. Reading it back gives a `Session`.
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from mharness.domain.catalog import Usd
from mharness.domain.messages import Message, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage

# Date and time in UTC, and 4 random hex digits: short to type, sorted by
# date, and two sessions in the same second do not clash.
_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")
# What /sessions shows of the first user message.
TITLE_MAX = 60


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
    """The tokens of one turn that called the model, however it ended, and
    what they cost (spec hito 7, §1.5)."""

    type: Literal["usage"] = "usage"
    usage: Usage
    # None without prices, and in the sessions of hito 6.
    cost: Usd | None = None


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
    # The sum of the turns with a cost, in USD, and how many had none.
    cost: Usd = Decimal(0)
    uncosted_turns: int = 0


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


class SessionExists(SessionError):
    """A new session's id is already taken: the conversation takes another
    (spec hito 7, §12)."""


class SessionNotFound(SessionError):
    """No session with that id."""


class SessionInUse(SessionError):
    """Another maha has the session open."""


class SessionCorrupt(SessionError):
    """The file cannot be read back as a session."""


def check_history(messages: list[Message]) -> None:
    """Raise `SessionCorrupt` unless the API would take `messages`: every
    tool call of the assistant has its result in the `tool` message right
    after it, and no result is left over (spec hito 6, §1.2). A session that
    fails this would get an error 400 on its first call."""
    # The ids of the calls still waiting for their results.
    waiting: list[str] = []
    for message in messages:
        if message.role == "tool":
            found = [b for b in message.blocks if isinstance(b, ToolResultBlock)]
            if len(found) != len(message.blocks):
                raise _broken("a tool message holds only results")
            for block in found:
                if block.call_id not in waiting:
                    raise _broken(f"result {block.call_id} without its call")
                waiting.remove(block.call_id)
            if waiting:
                raise _broken(f"call {waiting[0]} has no result")
            continue
        if waiting:
            raise _broken(f"call {waiting[0]} has no result")
        if message.role == "assistant":
            waiting = [b.id for b in message.blocks if isinstance(b, ToolCallBlock)]
    if waiting:
        raise _broken(f"call {waiting[0]} has no result")


def _broken(problem: str) -> SessionCorrupt:
    return SessionCorrupt(f"history: {problem}")


def replay(header: SessionHeader, entries: list[SessionEntry]) -> Session:
    """The session that `entries`, in the order of the file, build. Raises
    `SessionCorrupt` if its history could not go to the model."""
    messages: list[Message] = []
    model = header.model
    usage = Usage()
    cost = Decimal(0)
    uncosted = 0
    for entry in entries:
        match entry:
            case MessageEntry(message=message):
                messages.append(message)
            case ModelEntry(model=changed):
                model = changed
            case UsageEntry(usage=more, cost=spent):
                usage += more
                if spent is None:
                    uncosted += 1
                else:
                    cost += spent
    check_history(messages)
    return Session(
        header=header,
        messages=messages,
        model=model,
        usage=usage,
        cost=cost,
        uncosted_turns=uncosted,
    )


def summarize(
    header: SessionHeader, entries: list[SessionEntry], updated_at: datetime
) -> SessionSummary:
    """The line of /sessions for a session, without checking its history:
    a broken one still shows, so it can be deleted."""
    messages = [entry.message for entry in entries if isinstance(entry, MessageEntry)]
    first = next((m.text for m in messages if m.role == "user"), "")
    title = first.split("\n", 1)[0]
    if len(title) > TITLE_MAX:
        title = title[: TITLE_MAX - 1] + "…"
    return SessionSummary(
        id=header.id,
        cwd=header.cwd,
        updated_at=updated_at,
        messages=len(messages),
        title=title,
    )
