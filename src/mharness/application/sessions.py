"""Sessions: every turn saved and traced, and conversations resumed (spec
hito 6, §1.6, §1.8 and §1.9; spec hito 7, §1.7).

The `Agent` knows nothing of the disk: `Conversation` wraps it, traces what
happens, and when a turn ends (also by Ctrl+C or an error) appends to the
session what the agent kept. `Sessions` starts, resumes, lists and deletes
them through the `SessionStore` and `TraceSink` ports.
"""

import asyncio
import secrets
from collections.abc import AsyncGenerator, Callable, Collection, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from mharness.application.agent import Agent
from mharness.application.traces import TraceSummary, summarize
from mharness.domain.agent_events import (
    AgentEvent,
    ModelCallFinished,
    TurnFinished,
    TurnStarted,
)
from mharness.domain.catalog import add_cost
from mharness.domain.events import TextDelta
from mharness.domain.messages import Message
from mharness.domain.model import Usage
from mharness.domain.session import (
    MessageEntry,
    ModelEntry,
    Session,
    SessionEntry,
    SessionError,
    SessionExists,
    SessionHeader,
    SessionInUse,
    SessionNotFound,
    SessionSummary,
    UsageEntry,
    is_session_id,
    session_id,
)
from mharness.domain.trace import (
    Secrets,
    TraceError,
    TraceEvent,
    TraceExists,
    TraceRecord,
    TurnFailed,
    TurnInterrupted,
    redact,
)
from mharness.ports.sessions import SessionLog, SessionStore
from mharness.ports.tracing import TraceLog, TraceSink

# Ids tried for a new session before giving up: each clash takes another.
ID_ATTEMPTS = 5

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
    traces: TraceSink
    # Masked in every trace record (spec hito 7, §1.8).
    masked: Secrets


class Conversation:
    """An `Agent` and the session where its turns go.

    What happens goes to one queue, in order: the messages and tokens of
    each turn, and each model change. The queue is written at the end of
    every turn, on `/model` and on `close()`; a write that fails keeps it
    whole for the next try (the store undoes a half write), and `unsaved`
    says why. The file is created with the first turn: opening maha and
    leaving does not leave an empty session.

    The tokens and the cost of a turn are those of its finished calls to
    the model: a turn cut after one call still paid for it.

    Every event but the pieces of text goes to the trace, masked, as it
    happens; how a turn ended badly too. The trace never cuts a turn: its
    first failure is told once (`trace_warning()`). A new session has its
    id from the start, so that its trace and its file share it; until one
    of them exists, a clash with another session takes a new id.
    """

    def __init__(
        self,
        store: SessionStore,
        agent: Agent,
        origin: _Origin,
        *,
        log: SessionLog | None = None,
        session: str | None = None,
        cost: Decimal = Decimal(0),
        uncosted_turns: int = 0,
    ) -> None:
        self._store = store
        self._agent = agent
        self._origin = origin
        self._log = log
        # When a new session started; its header says so. `_new_id()` sets
        # it again with each id it takes.
        self._created = origin.now()
        self.id = session if session is not None else self._id_at(self._created)
        # Whether the id is ours: a resumed session, or a new one whose
        # trace or file was created. Until then, a clash takes another id.
        self._reserved = session is not None
        # Whether its session file exists: resumed, or created.
        self._stored = session is not None
        self._trace: TraceLog | None = None
        # The first failure of the trace, until it is told.
        self._trace_problem: str | None = None
        self._trace_failed = False
        # The turn in progress, and whether its start is in the trace: one
        # that opens late starts with it anyway (audit of hito 7, 11).
        self._turn = TurnStarted(text="")
        self._turn_at = self._created
        self._turn_traced = True
        # The model a new session's header names: the one it started with.
        self._first_model = agent.model
        # How many messages of the agent are already queued or saved.
        self._queued = len(agent.messages)
        # What happened and is not in the file yet, in order.
        self._pending: list[SessionEntry] = []
        # Why the last save failed; None once it works.
        self.unsaved: str | None = None
        # The session's cost so far, in USD, and the turns without one.
        self.cost = cost
        self.uncosted_turns = uncosted_turns

    @property
    def model(self) -> str:
        return self._agent.model

    @property
    def exists(self) -> bool:
        """Whether the id is this conversation's: resumed, or its trace or
        its file created. Before that, another session may have it."""
        return self._reserved

    @property
    def stored(self) -> bool:
        """Whether its session file exists, and can be resumed."""
        return self._stored

    @property
    def messages(self) -> Sequence[Message]:
        return self._agent.messages

    async def run(self, text: str) -> AsyncGenerator[AgentEvent]:
        """`Agent.run()`, and then the turn saved, however it ends."""
        usage = Usage()
        calls = 0
        # None once a call has no price.
        cost: Decimal | None = Decimal(0)
        # Once the turn finished, what comes after is not about it.
        finished = False
        # Whether the turn's cost is already in the session's.
        counted = False
        self._turn = TurnStarted(text=text)
        self._turn_at = self._origin.now()
        self._turn_traced = False
        try:
            async with aclosing(self._agent.run(text)) as events:
                async for event in events:
                    if isinstance(event, ModelCallFinished):
                        calls += 1
                        usage += event.usage
                        cost = add_cost(cost, event.cost)
                    if not isinstance(event, TextDelta):
                        await self._record(event)
                    finished = isinstance(event, TurnFinished)
                    if finished and calls:
                        # Before it is shown: the terminal tells the session's
                        # cost with this turn in it.
                        self._count(cost)
                        counted = True
                    yield event
        except BaseException as exc:
            if not finished:
                # Cut before it finished: Ctrl+C (CancelledError while
                # waiting, KeyboardInterrupt), its reader closing it
                # (GeneratorExit), or a time limit. Anything else failed.
                cut = isinstance(
                    exc, asyncio.CancelledError | GeneratorExit | KeyboardInterrupt
                )
                await self._record(
                    TurnInterrupted()
                    if cut
                    else TurnFailed(kind=type(exc).__name__, message=str(exc))
                )
            raise
        finally:
            fresh = self._agent.messages[self._queued :]
            self._queued += len(fresh)
            self._pending += [MessageEntry(message=m) for m in fresh]
            if calls:
                self._pending.append(UsageEntry(usage=usage, cost=cost))
                if not counted:
                    self._count(cost)
            await self._save()
            await self._sync_trace()

    def _count(self, cost: Decimal | None) -> None:
        """Add one turn's cost to the session's."""
        if cost is None:
            self.uncosted_turns += 1
        else:
            self.cost += cost

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
        if self._trace is not None:
            await self._trace.close()
            self._trace = None

    def trace_warning(self) -> str | None:
        """Why the trace failed, the first time it did; then None, even if
        it fails again: the person is told once."""
        problem, self._trace_problem = self._trace_problem, None
        return problem

    async def _record(self, event: TraceEvent) -> None:
        try:
            if self._trace is None:
                self._trace = await self._open_trace()
            log = self._trace
            if not self._turn_traced and not isinstance(event, TurnStarted):
                await self._write(log, self._turn_at, self._turn)
                self._turn_traced = True
            await self._write(log, self._origin.now(), event)
            if isinstance(event, TurnStarted):
                self._turn_traced = True
        except TraceError as exc:
            self._trace_trouble(exc)

    async def _write(self, log: TraceLog, at: datetime, event: TraceEvent) -> None:
        record = TraceRecord(at=at, session=self.id, event=event)
        try:
            masked = redact(record, self._origin.masked)
        except ValueError as exc:
            # A secret equal to a fixed value ("tool_call"): masked, the
            # record is no longer one. It is lost, never the turn.
            raise TraceError(f"cannot trace a {event.type} event: {exc}") from None
        await log.write(masked)

    async def _open_trace(self) -> TraceLog:
        """The trace of this session. A new session takes an id that no
        session has, and reserves it creating its trace only if there is
        none; another maha cannot create a session with that id in
        between, because it would need that same trace first."""
        traces = self._origin.traces
        if self._reserved:
            return await traces.open(self.id)
        for _ in range(ID_ATTEMPTS):
            if await self._store.exists(self.id):
                # A session without a trace (of hito 6) has it.
                self.id = self._new_id()
                continue
            try:
                log = await traces.open(self.id, new=True)
            except TraceExists:
                self.id = self._new_id()
                continue
            self._reserved = True
            return log
        raise TraceError(f"no free id for a new trace after {ID_ATTEMPTS} tries")

    async def _sync_trace(self) -> None:
        if self._trace is None:
            return
        try:
            await self._trace.sync()
        except TraceError as exc:
            self._trace_trouble(exc)

    def _trace_trouble(self, exc: TraceError) -> None:
        if not self._trace_failed:
            self._trace_failed = True
            self._trace_problem = str(exc)

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
        """The session's file, with this conversation's id. If a session
        that has no trace (one of hito 6) took it, another id, and the
        trace goes with it."""
        for _ in range(ID_ATTEMPTS):
            header = SessionHeader(
                id=self.id,
                created_at=self._created,
                cwd=self._origin.cwd,
                provider=self._origin.provider,
                model=self._first_model,
                maha=self._origin.version,
            )
            try:
                log = await self._store.create(header)
            except SessionExists:
                await self._take_another_id()
                continue
            self._reserved = True
            self._stored = True
            return log
        raise SessionError(f"no free id for a new session after {ID_ATTEMPTS} tries")

    async def _take_another_id(self) -> None:
        """Leave an id that a session already has. The trace written so far
        is this conversation's alone (it was created new): it moves."""
        old = self.id
        self.id = self._new_id()
        if not self._reserved:
            return
        # The trace is reserved again under the new id when it moves.
        self._reserved = False
        traces = self._origin.traces
        if self._trace is not None:
            await self._trace.close()
            self._trace = None
        try:
            records = await traces.read(old)
            self._trace = await self._open_trace()
            for record in records:
                await self._trace.write(record.model_copy(update={"session": self.id}))
        except TraceError as exc:
            self._trace_trouble(exc)
        # Moved or not, it never stays under an id that another session has.
        try:
            await traces.delete(old)
        except TraceError as exc:
            self._trace_trouble(exc)

    def _new_id(self) -> str:
        self._created = self._origin.now()
        return self._id_at(self._created)

    def _id_at(self, created: datetime) -> str:
        return session_id(created, self._origin.token())


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


@dataclass(frozen=True)
class TraceReport:
    """What /trace shows: the summary, and where the whole trace is."""

    summary: TraceSummary
    location: str


class Sessions:
    """Starts, resumes, lists and deletes the sessions of this maha, and
    reads their traces."""

    def __init__(
        self,
        store: SessionStore,
        new_agent: NewAgent,
        *,
        cwd: str,
        provider: str,
        model: str,
        version: str,
        traces: TraceSink,
        masked: Collection[str] = (),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        token: Callable[[], str] = lambda: secrets.token_hex(2),
    ) -> None:
        self._store = store
        self._new_agent = new_agent
        self._model = model
        self._origin = _Origin(
            cwd, provider, version, now, token, traces, Secrets(masked)
        )

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
            if _is_current(session, current):
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
            self._store,
            agent,
            self._origin,
            log=log,
            session=header.id,
            cost=loaded.cost,
            uncosted_turns=loaded.uncosted_turns,
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
        """The session and its trace; also a trace left without its session
        (its first turn could not be saved), which keeps that prompt."""
        if _is_current(session, current):
            raise SessionError("this is the current session")
        traces = self._origin.traces
        try:
            await self._store.delete(session)
        except SessionNotFound:
            if not await self._has_trace(session):
                raise
        try:
            await traces.delete(session)
        except TraceError as exc:
            raise SessionError(
                f"session {session} deleted, but not its trace: {exc}"
            ) from None

    async def trace(self, session: str | None, *, current: Conversation) -> TraceReport:
        """The trace of `session`, of any directory, or of the current one.
        It only reads: a session open in another maha has its trace too.
        Raises `TraceError`."""
        target = session if session is not None else current.id
        traces = self._origin.traces
        # Before its first turn the id is not yet the current one's: another
        # session may have it.
        own = session is not None or current.exists
        records = await traces.read(target) if own else []
        if (
            session is not None
            and not records
            and not await self._store.exists(session)
        ):
            raise TraceError(f"no session {session}")
        return TraceReport(summarize(target, records), traces.location(target))

    async def _has_trace(self, session: str) -> bool:
        try:
            return bool(await self._origin.traces.read(session))
        except TraceError:
            # Unreadable is still there, and delete says if it cannot; an id
            # of another form has nothing.
            return is_session_id(session)

    async def _open_last_here(
        self, current: Conversation
    ) -> tuple[Session, SessionLog]:
        """The newest session of this directory but the current one, skipping
        those open in another maha (final audit of hito 6, 3)."""
        busy = False
        for summary in await self._store.summaries():
            if not self.here(summary) or _is_current(summary.id, current):
                continue
            try:
                return await self._store.open(summary.id)
            except SessionInUse:
                busy = True
        if busy:
            raise SessionInUse("the other sessions here are open in another maha")
        raise SessionNotFound("no other session in this directory")


def _is_current(session: str, current: Conversation) -> bool:
    # A new conversation's id is not its own until it exists.
    return current.exists and session == current.id
