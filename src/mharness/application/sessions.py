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
    SessionEntry,
    SessionError,
    SessionHeader,
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

    The file is created with the first turn: opening maha and leaving does
    not leave an empty session. A save that fails does not cut the
    conversation: `unsaved` says why, and the next turn tries again with
    everything not saved yet.
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
        # How many messages of the agent are in the file.
        self._saved = len(agent.messages)
        # Tokens of finished turns not in the file yet.
        self._usage: list[Usage] = []
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
        try:
            async with aclosing(self._agent.run(text)) as events:
                async for event in events:
                    if isinstance(event, TurnFinished):
                        self._usage.append(event.usage)
                    yield event
        finally:
            await self._save()

    async def switch_model(self, model: str) -> None:
        """Use `model` from the next turn on. Saved at once, so the file
        keeps its place among the turns; before the first turn the header
        will carry it."""
        self._agent.model = model
        if self._log is not None:
            await self._write([ModelEntry(model=model)])

    async def close(self) -> None:
        """Save what is still pending, and let other maha resume or delete
        it. If saving fails again, `unsaved` says so."""
        await self._save()
        if self._log is not None:
            await self._log.close()
            self._log = None

    async def _save(self) -> None:
        messages = self._agent.messages[self._saved :]
        if not messages and not self._usage:
            return
        entries: list[SessionEntry] = [MessageEntry(message=m) for m in messages]
        entries += [UsageEntry(usage=usage) for usage in self._usage]
        if await self._write(entries):
            self._saved += len(messages)
            self._usage = []

    async def _write(self, entries: list[SessionEntry]) -> bool:
        """Append `entries`, creating the session first if needed. False,
        and `unsaved` set, if the store failed."""
        try:
            if self._log is None:
                self._log = await self._create()
            await self._log.append(entries)
        except SessionError as exc:
            self.unsaved = str(exc)
            return False
        self.unsaved = None
        return True

    async def _create(self) -> SessionLog:
        origin = self._origin
        created = origin.now()
        header = SessionHeader(
            id=session_id(created, origin.token()),
            created_at=created,
            cwd=origin.cwd,
            provider=origin.provider,
            model=self._agent.model,
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

    async def start(self) -> Conversation:
        """A new conversation; its session is created with the first turn."""
        return Conversation(self._store, self._new_agent(self._model, ()), self._origin)

    async def resume(self, session: str | None, *, current: Conversation) -> Resumed:
        """Open `session` (without id, the last one of this directory) and
        close `current`. A fresh agent: the approvals do not come back
        (spec hito 6, §1.9)."""
        if session is None:
            session = await self._last_here()
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

    async def _last_here(self) -> str:
        for summary in await self._store.summaries():
            if self.here(summary):
                return summary.id
        raise SessionNotFound("no session in this directory")
