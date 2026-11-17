"""A saved conversation and what its file holds (DESIGN §5, spec hito 6,
§1.2).

A session file is a header and then entries, one per line, only ever
appended: the messages of each turn, the tokens it used, and the model
changes. Reading it back gives a `Session`.

The format only grows (spec hito 11, §1.12): each version may add types of
entry or optional fields, and never changes what one that exists means. An
entry of a type this maha does not know is of a newer one: `SessionTooNew`,
not a broken file.
"""

import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from mharness.domain.messages import Message, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.money import Usd, known

# Date and time in UTC, and 4 random hex digits: short to type, sorted by
# date, and two sessions in the same second do not clash.
_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")
# The longest title, and what /sessions shows of the first user message.
TITLE_MAX = 60
# Around a title a model may write: quotes, markdown, a full stop.
_WRAPPING = "\"'`*#_«»\u201c\u201d\u2018\u2019 "
_LABEL = re.compile(r"^(title|título)\s*:\s*", re.IGNORECASE)


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
    # How many turns it stands for: one, but an import writes the turns
    # without a price in a single entry (audit of hito 8).
    turns: int = Field(default=1, ge=1, exclude_if=lambda turns: turns == 1)


class ModelEntry(BaseModel, frozen=True):
    """`/model` or `-m` changed the model from here on, for the maha of
    `provider`: a session resumed by another provider names a model of
    that one, which the API of the header's never gets (audit after hito
    9, S2)."""

    type: Literal["model"] = "model"
    model: str
    # None in older files: the header's.
    provider: str | None = Field(default=None, exclude_if=lambda p: p is None)


class TitleEntry(BaseModel, frozen=True):
    """The session's title from here on (spec hito 10, §1.12): written by
    the small model after the first turn, or by the person (`/rename`). A
    title by hand is never replaced by one written by the model."""

    type: Literal["title"] = "title"
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    manual: bool = False


class ArchiveEntry(BaseModel, frozen=True):
    """The first `replaces` messages of the conversation left the working
    window: `index` stands for them from here on (spec hito 11, §1.12).
    The messages stay in the file: `/export` gives them all."""

    type: Literal["archive"] = "archive"
    replaces: int = Field(ge=1)
    # The message that goes in their place (§1.8).
    index: Message
    # By /compact.
    manual: bool = Field(default=False, exclude_if=lambda manual: not manual)
    # The archivist's index, which it takes in the next time, and its
    # summary of these steps alone; None if it failed.
    notes: str | None = None
    summary: str | None = None


class OutputEntry(BaseModel, frozen=True):
    """A tool output too big for the context, whole: the archive is made
    again from here (spec hito 11, §1.5). The model got its ends and `id`."""

    type: Literal["output"] = "output"
    id: str
    # The index of its message in the conversation.
    position: int = Field(ge=0)
    tool: str | None = None
    text: str


# Validated by `type`, as the blocks of a message.
type SessionEntry = Annotated[
    MessageEntry | UsageEntry | ModelEntry | TitleEntry | ArchiveEntry | OutputEntry,
    Field(discriminator="type"),
]

# The types of entry this maha knows; another one is of a newer maha.
ENTRY_TYPES = frozenset({"message", "usage", "model", "title", "archive", "output"})


class Session(BaseModel, frozen=True):
    """A session read back from its file."""

    header: SessionHeader
    messages: list[Message]
    # The last one of the header's provider: the header's, or that of its
    # last `ModelEntry`.
    model: str
    # The sum of every `UsageEntry`.
    usage: Usage
    # The sum of the turns with a cost, in USD, and how many had none.
    cost: Usd = Decimal(0)
    uncosted_turns: int = Field(default=0, ge=0)
    # The last model of every provider that changed it, the header's too;
    # empty in the exports before it. An import takes only `model`, with
    # the header's provider.
    models: dict[str, str] = Field(default_factory=dict)
    # Its last title, and whether the person gave it; None: none yet.
    title: TitleEntry | None = None
    # Each time it archived, in order, and the outputs too big for the
    # context, whole (spec hito 11, §1.12); empty before hito 11.
    archives: list[ArchiveEntry] = Field(default_factory=list)
    outputs: list[OutputEntry] = Field(default_factory=list)

    @property
    def archived(self) -> int:
        """How many messages, from the start, the last index stands for."""
        return self.archives[-1].replaces if self.archives else 0

    @property
    def working(self) -> list[Message]:
        """What the model gets of the conversation: the last index and the
        messages after what it stands for."""
        if not self.archives:
            return list(self.messages)
        last = self.archives[-1]
        return [last.index, *self.messages[last.replaces :]]


class SessionSummary(BaseModel, frozen=True):
    """What `/sessions` shows of a session."""

    id: str
    cwd: str
    updated_at: datetime
    messages: int
    # Its title, or the first line of the first user message, cut.
    title: str
    # Why it cannot be read, if it cannot: listed all the same, so that it
    # can be deleted, and never skipped in silence (audit after hito 10, S2).
    unreadable: str | None = None


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


class SessionTooNew(SessionError):
    """The file has entries of a newer maha, which this one cannot read
    (spec hito 11, §1.12)."""


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


def whole_turns(entries: Sequence[SessionEntry]) -> int:
    """How many of `entries`, from the start, to keep: all of them, unless
    a crash cut the last turn between two of its lines and left an
    assistant's calls without their results (audit after hito 9, S1).
    Then that turn goes, from its user message on: the agent keeps whole
    turns, and a call never comes without its result. Damage anywhere
    else is left for `replay` to find."""
    last = entries[-1] if entries else None
    if not isinstance(last, MessageEntry) or not _calls(last.message):
        # A turn is written messages first: anything after its last
        # message means the messages were all written.
        return len(entries)
    for index in range(len(entries) - 2, -1, -1):
        entry = entries[index]
        if isinstance(entry, MessageEntry) and entry.message.role == "user":
            return index
    return len(entries) - 1


def _calls(message: Message) -> bool:
    """Whether `message` is the assistant's and calls tools."""
    return message.role == "assistant" and any(
        isinstance(block, ToolCallBlock) for block in message.blocks
    )


def _broken(problem: str) -> SessionCorrupt:
    return SessionCorrupt(f"history: {problem}")


def replay(header: SessionHeader, entries: list[SessionEntry]) -> Session:
    """The session that `entries`, in the order of the file, build. Raises
    `SessionCorrupt` if its history could not go to the model."""
    messages: list[Message] = []
    models = {header.provider: header.model}
    usage = Usage()
    cost = Decimal(0)
    uncosted = 0
    title: TitleEntry | None = None
    archives: list[ArchiveEntry] = []
    outputs: list[OutputEntry] = []
    for entry in entries:
        match entry:
            case MessageEntry(message=message):
                messages.append(message)
            case ArchiveEntry(replaces=replaces):
                # Of messages written before it, and never fewer than the
                # last time: an index stands for a start of the conversation.
                if replaces > len(messages):
                    raise _broken(f"an archive of {replaces} messages, past the end")
                if archives and replaces < archives[-1].replaces:
                    raise _broken("an archive goes back")
                archives.append(entry)
            case OutputEntry():
                outputs.append(entry)
            case TitleEntry():
                title = latest_title(title, entry)
            case ModelEntry(model=changed, provider=provider):
                models[provider or header.provider] = changed
            case UsageEntry(usage=more, cost=spent, turns=turns):
                usage += more
                # A sum past what an amount in USD can be is no longer
                # known (review of the deep audit).
                if spent is None or known(cost + spent) is None:
                    uncosted += turns
                else:
                    cost += spent
    check_history(messages)
    if archives:
        # What the model gets has to be a history the API takes too.
        last = archives[-1]
        check_history([last.index, *messages[last.replaces :]])
    return Session(
        header=header,
        messages=messages,
        model=models[header.provider],
        usage=usage,
        cost=cost,
        uncosted_turns=uncosted,
        models=models,
        title=title,
        archives=archives,
        outputs=outputs,
    )


def summarize(
    header: SessionHeader, entries: list[SessionEntry], updated_at: datetime
) -> SessionSummary:
    """The line of /sessions for a session, without checking its history:
    a broken one still shows, so it can be deleted."""
    messages = [entry.message for entry in entries if isinstance(entry, MessageEntry)]
    titled: TitleEntry | None = None
    for entry in entries:
        if isinstance(entry, TitleEntry):
            titled = latest_title(titled, entry)
    if titled is not None:
        title = titled.title
    else:
        first = next((m.text for m in messages if m.role == "user"), "")
        title = _cut(first.split("\n", 1)[0])
    return SessionSummary(
        id=header.id,
        cwd=header.cwd,
        updated_at=updated_at,
        messages=len(messages),
        title=title,
    )


def latest_title(current: TitleEntry | None, new: TitleEntry) -> TitleEntry:
    """The title once `new` comes: a title by hand stays until another one
    by hand."""
    if current is not None and current.manual and not new.manual:
        return current
    return new


def clean_title(text: str) -> str | None:
    """`text` as a title: its first line with text, without control
    characters, quotes, markdown or a final full stop, and cut at
    `TITLE_MAX`; None if nothing is left. What a model writes may hold
    anything (spec hito 10, §1.12)."""
    for line in text.splitlines():
        shown = "".join(
            " " if unicodedata.category(char).startswith("C") else char for char in line
        )
        title = " ".join(shown.split()).strip(_WRAPPING)
        title = _LABEL.sub("", title).strip(_WRAPPING).rstrip(".").strip(_WRAPPING)
        if title:
            return _cut(title)
    return None


def _cut(title: str) -> str:
    return title if len(title) <= TITLE_MAX else title[: TITLE_MAX - 1] + "…"
