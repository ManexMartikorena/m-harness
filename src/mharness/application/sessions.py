"""Sessions: every turn saved, and conversations resumed (spec hito 6, §1.6,
§1.8 and §1.9).

The `Agent` knows nothing of the disk: `Conversation` wraps it and, when a
turn ends (also by Ctrl+C or an error), appends to the session what the
agent kept. `Sessions` starts, resumes, lists and deletes them through the
`SessionStore` port.
"""

import secrets
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime

from mharness.application.agent import Agent
from mharness.domain.agent_events import AgentEvent, TurnFinished
from mharness.domain.messages import Message
from mharness.domain.model import Usage
from mharness.domain.session import (
    MessageEntry,
    ModelEntry,
    Session,
    SessionEntry,
    SessionError,
    SessionHeader,
    SessionInUse,
    SessionNotFound,
    SessionSummary,
    UsageEntry,
    session_id,
)
from mharness.ports.sessions import SessionLog, SessionStore

# Builds the agent of a conversation: its model and the history it starts
# with. Which client and tools it has is not this module's business.
type NewAgent = Callable[[str, Sequence[Message]], Agent]


@dataclass(frozen=True)
class _Origin:
    """What every new session of this maha says about itself."""

    cwd: str
    provider: str
    version: str
    now: Callable[[], datetime]
    token: Callable[[], str]


class Conversation:
    """An `Agent` and the session where its turns go.

    What happens goes to one queue, in order: the messages and tokens of
    each turn, and each model change. The queue is written at the end of
    every turn, on `/model` and on `close()`; a write that fails keeps it
    whole for the next try (the store undoes a half write), and `unsaved`
    says why. The file is created with the first turn: opening maha and
    leaving does not leave an empty session.
    """

    def __init__(
        self,
        store: SessionStore,
        agent: Agent,
        origin: _Origin,
        *,
        log: SessionLog | None = None,
        session: str | None = None,
    ) -> None:
        self._store = store
        self._agent = agent
        self._origin = origin
        self._log = log
        self.id = session
        # The model a new session's header names: the one it started with.
        self._first_model = agent.model
        # How many messages of the agent are already queued or saved.
        self._queued = len(agent.messages)
        # What happened and is not in the file yet, in order.
        self._pending: list[SessionEntry] = []
        # Why the last save failed; None once it works.
        self.unsaved: str | None = None

    @property
    def model(self) -> str:
        return self._agent.model

    @property
    def messages(self) -> Sequence[Message]:
        return self._agent.messages

    async def run(self, text: str) -> AsyncGenerator[AgentEvent]:
        """`Agent.run()`, and then the turn saved, however it ends."""
        usage: Usage | None = None
        try:
            async with aclosing(self._agent.run(text)) as events:
                async for event in events:
                    if isinstance(event, TurnFinished):
                        usage = event.usage
                    yield event
        finally:
            fresh = self._agent.messages[self._queued :]
            self._queued += len(fresh)
            self._pending += [MessageEntry(message=m) for m in fresh]
            if usage is not None:
                self._pending.append(UsageEntry(usage=usage))
            await self._save()

    async def switch_model(self, model: str) -> None:
        """Use `model` from the next turn on; the change keeps its place
        among the turns (final audit of hito 6, 4)."""
        self._agent.model = model
        self._pending.append(ModelEntry(model=model))
        await self._save()

    async def close(self) -> None:
        """Save what is still pending, and let other maha resume or delete
        it. If saving fails again, `unsaved` says so."""
        await self._save()
        if self._log is not None:
            await self._log.close()
            self._log = None

    async def _save(self) -> None:
        if not self._pending:
            return
        if self._log is None and not any(
            isinstance(entry, MessageEntry) for entry in self._pending
        ):
            # No turn yet: a model change alone does not make a session.
            return
        try:
            if self._log is None:
                self._log = await self._create()
            await self._log.append(self._pending)
        except SessionError as exc:
            self.unsaved = str(exc)
            return
        self._pending = []
        self.unsaved = None

    async def _create(self) -> SessionLog:
        origin = self._origin
        created = origin.now()
        header = SessionHeader(
            id=session_id(created, origin.token()),
            created_at=created,
            cwd=origin.cwd,
            provider=origin.provider,
            model=self._first_model,
            maha=origin.version,
        )
        log = await self._store.create(header)
        self.id = header.id
        return log


@dataclass(frozen=True)
class Resumed:
    """A resumed session, and what the person should be told about it."""

    conversation: Conversation
    messages: int
    # The directory of the session, if it is not this one: the tools work
    # here, not there.
    other_cwd: str | None
    # The model of the session, if it is of another provider and the
    # configured one is used instead.
    fallback_from: str | None
    # Whether the last answer was cut by Ctrl+C.
    interrupted: bool
    # Why the session left behind could not save what it still had; it is
    # lost (final audit of hito 6, 5).
    left_unsaved: str | None = None


class Sessions:
    """Starts, resumes, lists and deletes the sessions of this maha."""

    def __init__(
        self,
        store: SessionStore,
        new_agent: NewAgent,
        *,
        cwd: str,
        provider: str,
        model: str,
        version: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        token: Callable[[], str] = lambda: secrets.token_hex(2),
    ) -> None:
        self._store = store
        self._new_agent = new_agent
        self._model = model
        self._origin = _Origin(cwd, provider, version, now, token)

    @property
    def cwd(self) -> str:
        """The directory where this maha runs, and its tools work."""
        return self._origin.cwd

    async def start(self) -> Conversation:
        """A new conversation; its session is created with the first turn."""
        return Conversation(self._store, self._new_agent(self._model, ()), self._origin)

    async def resume(self, session: str | None, *, current: Conversation) -> Resumed:
        """Open `session` and close `current`. Without id, the newest other
        session of this directory that no other maha has open. A fresh
        agent: the approvals do not come back (spec hito 6, §1.9)."""
        if session is None:
            loaded, log = await self._open_last_here(current)
        else:
            if session == current.id:
                raise SessionError("this is the current session")
            loaded, log = await self._store.open(session)
        header = loaded.header
        same_provider = header.provider == self._origin.provider
        model = loaded.model if same_provider else self._model
        try:
            agent = self._new_agent(model, loaded.messages)
        except BaseException:
            await log.close()
            raise
        conversation = Conversation(
            self._store, agent, self._origin, log=log, session=header.id
        )
        # The new one is ready: only now is the current one let go.
        await current.close()
        last = loaded.messages[-1] if loaded.messages else None
        return Resumed(
            conversation=conversation,
            messages=len(loaded.messages),
            other_cwd=None if header.cwd == self._origin.cwd else header.cwd,
            fallback_from=None if same_provider else loaded.model,
            interrupted=last is not None and last.interrupted,
            left_unsaved=current.unsaved,
        )

    async def summaries(self) -> list[SessionSummary]:
        """Every session, of every directory, newest first."""
        return await self._store.summaries()

    def here(self, summary: SessionSummary) -> bool:
        """Whether the session was in this directory."""
        return summary.cwd == self._origin.cwd

    async def delete(self, session: str, *, current: Conversation) -> None:
        if session == current.id:
            raise SessionError("this is the current session")
        await self._store.delete(session)

    async def _open_last_here(
        self, current: Conversation
    ) -> tuple[Session, SessionLog]:
        """The newest session of this directory but the current one, skipping
        those open in another maha (final audit of hito 6, 3)."""
        busy = False
        for summary in await self._store.summaries():
            if not self.here(summary) or summary.id == current.id:
                continue
            try:
                return await self._store.open(summary.id)
            except SessionInUse:
                busy = True
        if busy:
            raise SessionInUse("the other sessions here are open in another maha")
        raise SessionNotFound("no other session in this directory")
