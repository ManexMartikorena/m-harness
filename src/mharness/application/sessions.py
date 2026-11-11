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
from contextlib import aclosing, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from mharness.application.agent import Agent
from mharness.application.prompt import SystemPromptBuilder
from mharness.application.titles import Titler
from mharness.application.traces import TraceSummary, summarize
from mharness.domain.agent_events import (
    AgentEvent,
    ModelCallFinished,
    TurnFinished,
    TurnStarted,
)
from mharness.domain.events import TextDelta
from mharness.domain.messages import Message
from mharness.domain.model import Effort, Usage
from mharness.domain.money import known
from mharness.domain.prompt import SystemPrompt
from mharness.domain.session import (
    MessageEntry,
    ModelEntry,
    Session,
    SessionCorrupt,
    SessionEntry,
    SessionError,
    SessionExists,
    SessionHeader,
    SessionInUse,
    SessionNotFound,
    SessionSummary,
    TitleEntry,
    UsageEntry,
    check_history,
    clean_title,
    is_session_id,
    session_id,
)
from mharness.domain.trace import (
    PromptLayerInfo,
    PromptUsed,
    Secrets,
    TitleWritten,
    TraceError,
    TraceEvent,
    TraceExists,
    TraceInUse,
    TraceRecord,
    TurnFailed,
    TurnInterrupted,
    redact,
)
from mharness.ports.sessions import SessionLog, SessionStore
from mharness.ports.tracing import TraceLog, TraceSink

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
    # Builds each session's system prompt; None: no system prompt.
    prompt: SystemPromptBuilder | None = None
    # Names each new session after its first turn; None: no titles (`-p`,
    # the evals; spec hito 10, §1.12).
    titler: Titler | None = None


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
        prompt: SystemPrompt | None = None,
        title: TitleEntry | None = None,
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
        # The system prompt of this session, fixed until the next (spec
        # hito 10, §1.2); its warnings are told when it opens.
        self.prompt = prompt
        agent.system = None if prompt is None else prompt.text
        agent.system_for = self._system_for
        # Traced with the next turn that starts (spec hito 10, §1.13).
        self._prompt_untraced = prompt is not None
        # Its title, and the call writing one in the background (§1.12).
        self.title = title
        self._titling: asyncio.Task[None] | None = None
        # The title is saved while a turn may run: one save at a time.
        self._saving = asyncio.Lock()

    def _system_for(self, model: str) -> str | None:
        """The session's prompt for `model`: its own family layer."""
        if self.prompt is None or self._origin.prompt is None:
            return None if self.prompt is None else self.prompt.text
        return self._origin.prompt.for_model(self.prompt, model).text

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

    @property
    def tools(self) -> list[str]:
        """The names of the tools the model has."""
        return self._agent.tool_names

    @property
    def effort(self) -> Effort | None:
        """How hard the model works in each call; None: the model's own."""
        return self._agent.effort

    @effort.setter
    def effort(self, effort: Effort | None) -> None:
        self._agent.effort = effort

    async def run(self, text: str) -> AsyncGenerator[AgentEvent]:
        """`Agent.run()`, and then the turn saved, however it ends."""
        usage = Usage()
        calls = 0
        # By call, as maha stats: what the calls with a price cost, and how
        # many had none (audit after hito 10, S3).
        cost = Decimal(0)
        priced = unpriced = 0
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
                        if event.cost is None:
                            unpriced += 1
                        else:
                            priced += 1
                            cost += event.cost
                    if not isinstance(event, TextDelta):
                        await self._record(event)
                    if isinstance(event, TurnStarted) and self._prompt_untraced:
                        await self._record(self._prompt_used())
                        self._prompt_untraced = False
                    finished = isinstance(event, TurnFinished)
                    if finished and calls:
                        # Before it is shown: the terminal tells the session's
                        # cost with this turn in it.
                        self._count(cost if priced else None, unpriced)
                        counted = True
                    yield event
        except BaseException as exc:
            if not finished:
                # Cut before it finished: Ctrl+C (CancelledError while
                # waiting, KeyboardInterrupt) or its reader closing it
                # (GeneratorExit). Anything else failed. A time limit
                # finishes the turn: it never comes here.
                cut = isinstance(
                    exc, asyncio.CancelledError | GeneratorExit | KeyboardInterrupt
                )
                # The call the cut stopped was paid: it counts (audit after
                # hito 10, B2).
                paid = self._agent.take_cut_call()
                if paid is not None:
                    calls += 1
                    usage += paid.usage
                    if paid.cost is None:
                        unpriced += 1
                    else:
                        priced += 1
                        cost += paid.cost
                    await self._record(paid)
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
                self._pending.append(
                    UsageEntry(usage=usage, cost=cost if priced else None)
                )
                if priced and unpriced:
                    # The calls without a price, as a turn without one: the
                    # session's cost is then at least what it says.
                    self._pending.append(UsageEntry(usage=Usage(), cost=None))
                if not counted:
                    self._count(cost if priced else None, unpriced)
            await self._save()
            await self._sync_trace()
            # Once its file exists: also if the first turn could not be
            # saved and a later one was (audit after hito 10, S5).
            if self._stored:
                self.name()

    def name(self) -> None:
        """Ask for the title in the background, from the first message, if
        the session has none yet: nobody waits for it."""
        titler = self._origin.titler
        if titler is None or self.title is not None or self._titling is not None:
            return
        first = next((m.text for m in self._agent.messages if m.role == "user"), "")
        if first:
            self._titling = asyncio.create_task(self._write_title(titler, first))

    async def _write_title(self, titler: Titler, first: str) -> None:
        title = await titler.title(first)
        if title is None:
            return
        if title.text is not None and (self.title is None or not self.title.manual):
            self.title = TitleEntry(title=title.text)
            self._pending.append(self.title)
        # Paid even if nothing usable came: its cost is the session's.
        self._pending.append(UsageEntry(usage=title.usage, cost=title.cost))
        self._count(title.cost)
        await self._record(
            TitleWritten(model=title.model, usage=title.usage, cost=title.cost)
        )
        await self._save()
        await self._sync_trace()

    @property
    def naming(self) -> bool:
        """Whether a title is on its way."""
        return self._titling is not None and not self._titling.done()

    async def titled(self) -> None:
        """Wait for the title on its way, if any. A title is never worth an
        error: one that failed in a way nobody expected is left (audit
        after hito 10, S4)."""
        if self._titling is not None:
            with suppress(Exception):
                await self._titling

    async def rename(self, title: str) -> str:
        """Give the session `title` by hand; the small model never replaces
        it. Returns it as kept; raises `SessionError` if nothing is left of
        it (spec hito 10, §1.12)."""
        kept = clean_title(title)
        if kept is None:
            raise SessionError("a title needs some text")
        self.title = TitleEntry(title=kept, manual=True)
        self._pending.append(self.title)
        await self._save()
        return kept

    def _prompt_used(self) -> PromptUsed:
        assert self.prompt is not None
        return PromptUsed(
            fingerprint=self.prompt.fingerprint,
            base=self.prompt.base_fingerprint,
            layers=tuple(
                PromptLayerInfo(
                    kind=layer.kind,
                    source=layer.source,
                    bytes=len(layer.text.encode("utf-8")),
                )
                for layer in self.prompt.layers
            ),
        )

    def _count(self, cost: Decimal | None, unpriced: int = 0) -> None:
        """Add what a turn's calls with a price cost to the session's; with
        calls without one, the turn counts as one without a cost too. Past
        what an amount in USD can be, the turn counts as one without a cost,
        as on resuming."""
        past = cost is not None and known(self.cost + cost) is None
        if cost is not None and not past:
            self.cost += cost
        if cost is None or past or unpriced:
            self.uncosted_turns += 1

    async def switch_model(self, model: str) -> None:
        """Use `model` from the next turn on; the change keeps its place
        among the turns (final audit of hito 6, 4)."""
        self._agent.model = model
        if self.prompt is not None and self._origin.prompt is not None:
            # Another model, maybe of another family (spec hito 10, §1.3).
            self.prompt = self._origin.prompt.for_model(self.prompt, model)
            self._agent.system = self.prompt.text
            self._prompt_untraced = True
        self._pending.append(ModelEntry(model=model, provider=self._origin.provider))
        await self._save()

    async def close(self) -> None:
        """Wait for a title on its way, save what is still pending, and let
        other maha resume or delete it. If saving fails again, `unsaved`
        says so. Ctrl+C while the title comes leaves without it, and the
        rest is still saved (decision of the maintainer, 2026-11-10)."""
        cut: asyncio.CancelledError | None = None
        if self._titling is not None:
            try:
                await self.titled()
            except asyncio.CancelledError as exc:
                cut = exc
                self._titling.cancel()
                with suppress(asyncio.CancelledError):
                    await self._titling
            self._titling = None
        await self._save()
        if self._log is not None:
            await self._log.close()
            self._log = None
        if self._trace is not None:
            await self._trace.close()
            self._trace = None
        if cut is not None:
            raise cut

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
        between, because it would need that same trace first. No cap on
        the tries (decision of the maintainer, spec hito 7, §12.34): the
        token is random, and a taken id never costs a record."""
        traces = self._origin.traces
        if self._reserved:
            return await traces.open(self.id)
        while True:
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
        async with self._saving:
            await self._save_pending()

    async def _save_pending(self) -> None:
        if not self._pending:
            return
        if self._log is None and not any(
            isinstance(entry, MessageEntry) for entry in self._pending
        ):
            # No turn yet: a model change alone does not make a session.
            return
        # Taken before the wait: what comes meanwhile (a title) stays for
        # the next save, never cleared unsaved (audit after hito 10, S1).
        batch, self._pending = self._pending, []
        try:
            if self._log is None:
                self._log = await self._create()
            await self._log.append(batch)
        except SessionError as exc:
            # In front: the order of the file is the order of what happened.
            self._pending[:0] = batch
            self.unsaved = str(exc)
            return
        except BaseException:
            self._pending[:0] = batch
            raise
        self.unsaved = None

    async def _create(self) -> SessionLog:
        """The session's file, with this conversation's id. If a session
        that has no trace (one of hito 6) took it, another id, and the
        trace goes with it. No cap on the tries, as in `_open_trace()`."""
        while True:
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
    # Without an id: newer sessions that cannot be read and whose directory
    # is unknown, so they may be this one's (review of the audit after
    # hito 10, S2).
    unknown: tuple[str, ...] = ()


@dataclass(frozen=True)
class Start:
    """Which conversation maha starts with (spec hito 8, §1.12)."""

    # The last session of this directory (-c), also one of `maha -p`.
    last: bool = False
    # A session by id, of any directory (-r).
    session: str | None = None
    # This model instead of the configured one, or the session's (-m).
    model: str | None = None


@dataclass(frozen=True)
class Opened:
    """The conversation maha starts with, and what to tell about the
    session it resumed, if it resumed one."""

    conversation: Conversation
    resumed: Resumed | None = None


@dataclass(frozen=True)
class TraceReport:
    """What /trace shows: the summary, and where the whole trace is."""

    summary: TraceSummary
    # None without a trace: an imported session, one of hito 6, or one
    # before its first turn (audit of hito 8).
    location: str | None


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
        model: str | None,
        version: str,
        traces: TraceSink,
        masked: Collection[str] = (),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        token: Callable[[], str] = lambda: secrets.token_hex(2),
        effort: Effort | None = None,
        prompt: SystemPromptBuilder | None = None,
        titler: Titler | None = None,
    ) -> None:
        self._store = store
        self._new_agent = new_agent
        self._model = model
        # This maha's: every conversation it opens takes it, and /effort
        # changes it (spec hito 9, §1.7).
        self.effort = effort
        self._origin = _Origin(
            cwd, provider, version, now, token, traces, Secrets(masked), prompt, titler
        )

    @property
    def cwd(self) -> str:
        """The directory where this maha runs, and its tools work."""
        return self._origin.cwd

    async def start(self, model: str | None = None) -> Conversation:
        """A new conversation, with `model` or the configured one; its
        session is created with the first turn. Raises `SessionError` if
        there is neither: the commands that never call the model run
        without one."""
        chosen = model or self._model
        if chosen is None:
            raise SessionError("no model configured")
        prompt = await self._build(chosen, None)
        agent = self._new_agent(chosen, ())
        agent.effort = self.effort
        return Conversation(self._store, agent, self._origin, prompt=prompt)

    async def open(self, start: Start | None = None) -> Opened:
        """The first conversation of this maha: a new one, or a session
        resumed as /resume does. Raises `SessionError` if it cannot be
        resumed."""
        start = start or Start()
        if not start.last and start.session is None:
            return Opened(await self.start(start.model))
        fresh = await self.start()
        resumed = await self.resume(start.session, current=fresh)
        # Nothing to save nor to name: it never had a turn.
        await fresh.close()
        conversation = resumed.conversation
        if start.model is not None and start.model != conversation.model:
            await conversation.switch_model(start.model)
        return Opened(conversation, resumed)

    async def resume(self, session: str | None, *, current: Conversation) -> Resumed:
        """Open `session`, to leave `current` for it. Without id, the newest
        other session of this directory that no other maha has open. A
        fresh agent: the approvals do not come back (spec hito 6, §1.9).

        `current` is not closed here: the caller switches first and closes
        it after, so that Ctrl+C while its title comes never leaves the
        caller on a closed conversation (review of the audit after hito
        10)."""
        if session is None:
            loaded, log, unknown = await self._open_last_here(current)
        else:
            if _is_current(session, current):
                raise SessionError("this is the current session")
            loaded, log = await self._store.open(session)
            unknown = ()
        header = loaded.header
        same_provider = header.provider == self._origin.provider
        # Of another provider, the model it chose last, if it ever resumed
        # this session; else the configured one (audit after hito 9, S2).
        own = loaded.models.get(self._origin.provider)
        model = loaded.model if same_provider else own or self._model
        try:
            if model is None:
                raise SessionError("no model configured")
            # Built again, here: the model learns where it works now.
            prompt = await self._build(model, header.cwd)
            agent = self._new_agent(model, loaded.messages)
            agent.effort = self.effort
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
            prompt=prompt,
            title=loaded.title,
        )
        # One left without a title gets it now (decision of the maintainer,
        # 2026-11-10).
        conversation.name()
        last = loaded.messages[-1] if loaded.messages else None
        return Resumed(
            conversation=conversation,
            messages=len(loaded.messages),
            other_cwd=None if header.cwd == self._origin.cwd else header.cwd,
            fallback_from=None if same_provider else loaded.model,
            interrupted=last is not None and last.interrupted,
            unknown=unknown,
        )

    async def _build(self, model: str, started_in: str | None) -> SystemPrompt | None:
        if self._origin.prompt is None:
            return None
        return await self._origin.prompt.build(model, started_in=started_in)

    async def summaries(self) -> list[SessionSummary]:
        """Every session, of every directory, newest first."""
        return await self._store.summaries()

    def here(self, summary: SessionSummary) -> bool:
        """Whether the session was in this directory."""
        return summary.cwd == self._origin.cwd

    async def read(self, session: str) -> Session:
        """A session of any directory, as it is on disk, without opening it:
        also one open in another maha. Raises `SessionError`."""
        return await self._store.read(session)

    async def import_session(self, session: Session) -> str:
        """Save `session`, exported by `maha export`, as a new session of
        this directory with an id of its own; never over another. Its
        history is untrusted input, as any: it brings no approvals (spec
        hito 6, §1.9). Raises `SessionError`."""
        check_history(session.messages)
        entries: list[SessionEntry] = [
            MessageEntry(message=message) for message in session.messages
        ]
        # What it cost, so that its total is the same; the turns without
        # a price, as such, in one entry: as many as it says take no more
        # room (audit of hito 8).
        if session.uncosted_turns:
            entries.append(
                UsageEntry(usage=Usage(), cost=None, turns=session.uncosted_turns)
            )
        if session.usage != Usage() or session.cost:
            entries.append(UsageEntry(usage=session.usage, cost=session.cost))
        if session.title is not None:
            # Its title, and whether the person gave it (spec hito 10, §1.12).
            entries.append(session.title)
        origin = self._origin
        # A trace left without its session keeps its id too, even empty.
        traced = set(await origin.traces.sessions())
        while True:
            created = origin.now()
            new = session_id(created, origin.token())
            if new in traced:
                continue
            header = SessionHeader(
                id=new,
                created_at=created,
                cwd=origin.cwd,
                provider=session.header.provider,
                model=session.model,
                maha=origin.version,
            )
            try:
                log = await self._store.create(header)
            except SessionExists:
                continue
            try:
                await log.append(entries)
            except BaseException:
                # Nothing half imported: the empty session goes too.
                await log.close()
                with suppress(SessionError):
                    await self._store.delete(new)
                raise
            await log.close()
            return new

    async def last_here(self) -> str:
        """The id of the newest session of this directory, open or not.
        Raises `SessionNotFound`."""
        for summary in await self._store.summaries():
            if self.here(summary):
                return summary.id
        raise SessionNotFound("no session in this directory")

    async def delete(
        self, session: str, *, current: Conversation | None = None
    ) -> None:
        """The session and its trace; also a trace left without its session
        (its first turn could not be saved), which keeps that prompt. From
        the shell there is no `current`."""
        if _is_current(session, current):
            raise SessionError("this is the current session")
        traces = self._origin.traces
        stored = True
        try:
            await self._store.delete(session)
        except SessionNotFound:
            if not await self._has_trace(session):
                raise
            stored = False
        try:
            await traces.delete(session)
        except TraceInUse:
            if stored:
                raise SessionError(
                    f"session {session} deleted, but not its trace: "
                    "another maha writes it"
                ) from None
            # Another maha in its first turn: no file yet, but the session
            # is that maha's (audit after hito 9, S3).
            raise SessionInUse(f"session {session} is open in another maha") from None
        except TraceError as exc:
            if not stored:
                # Only a trace, and it stays: nothing was deleted (audit
                # after hito 10, S6).
                raise SessionError(str(exc)) from None
            raise SessionError(
                f"session {session} deleted, but not its trace: {exc}"
            ) from None

    async def trace(
        self, session: str | None, *, current: Conversation | None = None
    ) -> TraceReport:
        """The trace of `session`, of any directory, or of the current one.
        It only reads: a session open in another maha has its trace too.
        Raises `TraceError`."""
        if session is not None:
            target, own = session, True
        elif current is not None:
            # Before its first turn the id is not yet the current one's:
            # another session may have it.
            target, own = current.id, current.exists
        else:
            raise TraceError("which session? Without a conversation, an id")
        traces = self._origin.traces
        records = await traces.read(target) if own else []
        if (
            session is not None
            and not records
            and not await self._store.exists(session)
        ):
            raise TraceError(f"no session {session}")
        location = traces.location(target) if records else None
        return TraceReport(summarize(target, records), location)

    async def _has_trace(self, session: str) -> bool:
        try:
            return bool(await self._origin.traces.read(session))
        except TraceError:
            # Unreadable is still there, and delete says if it cannot; an id
            # of another form has nothing.
            return is_session_id(session)

    async def _open_last_here(
        self, current: Conversation
    ) -> tuple[Session, SessionLog, tuple[str, ...]]:
        """The newest session of this directory but the current one, skipping
        those open in another maha (final audit of hito 6, 3); and the newer
        unreadable ones of unknown directory, to be told."""
        busy = False
        unknown: list[str] = []
        for summary in await self._store.summaries():
            if summary.unreadable is not None and not summary.cwd:
                unknown.append(summary.id)
                continue
            if not self.here(summary) or _is_current(summary.id, current):
                continue
            if summary.unreadable is not None:
                # Never another one in its place, in silence (audit after
                # hito 10, S2).
                raise SessionCorrupt(
                    f"the last session here, {summary.id}, cannot be read "
                    f"({summary.unreadable}): /delete it, or resume another "
                    "by its id"
                )
            try:
                loaded, log = await self._store.open(summary.id)
            except SessionInUse:
                busy = True
                continue
            return loaded, log, tuple(unknown)
        # At the start, the current one is new: there is no "other".
        other = "other " if current.stored else ""
        if busy:
            raise SessionInUse(f"the {other}sessions here are open in another maha")
        raise SessionNotFound(f"no {other}session in this directory")


def _is_current(session: str, current: Conversation | None) -> bool:
    # A new conversation's id is not its own until it exists.
    return current is not None and current.exists and session == current.id
