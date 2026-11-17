"""The agent loop: call the model, run the tools it asks for, repeat
(DESIGN §4, spec hito 4, §1.7, and spec hito 5, §1.4).

The model only proposes calls; this code validates them, asks the user when
the tool needs it, and runs them.
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from mharness.application.approvals import SessionApprovals
from mharness.application.collect import Accumulator
from mharness.application.context import Archived, Archivist
from mharness.application.pricing import call_cost
from mharness.application.recall import ArchiveSlot
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import (
    AgentEvent,
    ApprovalCovered,
    ApprovalRequested,
    ContextArchived,
    ContextArchiving,
    ModelCallFinished,
    ModelFallback,
    ModelRetry,
    ToolCallProposed,
    ToolFinished,
    TurnEnd,
    TurnFinished,
    TurnStarted,
)
from mharness.domain.approval import ApprovalRequest, Decision
from mharness.domain.archive import ArchiveError, ArchiveItem, ArchiveNotes
from mharness.domain.catalog import add_cost
from mharness.domain.context import (
    DEFAULT_BUDGET,
    OUTPUT_LIMIT,
    ContextPolicy,
    ContextUsage,
    archive_cut,
    archive_index,
    archive_items,
    estimate,
    estimate_messages,
    estimate_tools,
    fit,
    message_text,
    step_starts,
    summary_item,
)
from mharness.domain.errors import (
    ContextOverflowError,
    ModelResponseError,
    RetryableModelError,
)
from mharness.domain.events import ModelEvent, TextDelta, UsageSoFar
from mharness.domain.limits import TurnLimits
from mharness.domain.messages import (
    Message,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from mharness.domain.model import (
    Effort,
    ModelRequest,
    ModelResponse,
    StopReason,
    ToolSpec,
    Usage,
)
from mharness.domain.retry import RetryPolicy
from mharness.domain.session import ArchiveEntry, OutputEntry
from mharness.domain.tools import ToolError
from mharness.ports.approval import ApprovalGate
from mharness.ports.archive import ContextArchive
from mharness.ports.catalog import ModelCatalog
from mharness.ports.model import ModelClient
from mharness.ports.tools import Tool

NOT_RUN_DENIED = "not run: a previous call was denied"
# What the call in progress gets when its step is cut short.
CANCELLED = "cancelled by the user"
INTERRUPTED = "interrupted by an internal error"
TIMED_OUT = "stopped by the time limit"
CONTEXT_FULL = "not run: the conversation filled your context window"
REFUSED = "not run: the provider refused your answer"

# A provider that cuts the prompt in silence (spec hito 11, decision 14)
# shows it in its count: below this share of what was sent, when that could
# not fit in the window; or, after a call it counted, below that call's
# prompt plus this share of what was added since, when that was at least
# `SILENT_GROWTH` tokens. A prompt holds the one before it whole, and text
# never has four times fewer tokens than characters / 4 says.
SILENT_CUT = 0.9
SILENT_SHARE = 0.25
SILENT_GROWTH = 1_000

# The only answers that run a call that asked, or deny it.
DECISIONS: tuple[Decision, ...] = ("once", "session", "deny")


class Agent:
    """A conversation with a model that can use tools, kept in memory.

    Every step sends the whole history, the turn so far and the tools. The
    `gate` decides on the calls that need approval; what the user approves
    for the whole session lives as long as the agent. `model` can change
    between turns (`/model`, spec hito 6, §1.8). The `catalog` prices each
    call for `provider` (spec hito 7, §1.6). Each turn stops at its
    `limits` (spec hito 8, §1.1). A call that fails before its first event
    with an error that may pass is made again, as `retry` says, after
    `sleep`; when the retries run out, with the `fallback` model, which
    then answers the rest of the turn (spec hito 8, §1.14).
    """

    def __init__(
        self,
        client: ModelClient,
        tools: ToolRegistry,
        *,
        gate: ApprovalGate,
        model: str,
        catalog: ModelCatalog,
        provider: str,
        limits: TurnLimits | None = None,
        history: Sequence[Message] = (),
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        fallback: str | None = None,
        effort: Effort | None = None,
        system: str | None = None,
        context_budget: int = DEFAULT_BUDGET,
        slot: ArchiveSlot | None = None,
        archivist: Archivist | None = None,
    ) -> None:
        self._client = client
        self._tools = tools
        self._gate = gate
        self._approvals = SessionApprovals()
        # The call a Ctrl+C cut, for the conversation to count.
        self._unseen_call: ModelCallFinished | None = None
        self.model = model
        self._catalog = catalog
        self._provider = provider
        self.limits = limits or TurnLimits()
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        self.fallback = fallback
        # In every call; /effort changes it (spec hito 9, §1.7).
        self.effort = effort
        # The session's system prompt, the same in every call; the session
        # sets it, and /model changes its family layer (spec hito 10, §1.2).
        self.system = system
        # The system prompt of another model of this session (the fallback),
        # with its own family layer; None: the same text for any model
        # (audit after hito 10, B5).
        self.system_for: Callable[[str], str | None] | None = None
        # A resumed session starts with its history (spec hito 6, §1.6); its
        # approvals do not come back (§1.9).
        self._messages: list[Message] = list(history)
        # The request of the call in progress, and the exact size of the
        # last one that answered (spec hito 11, §1.2).
        self._sent: ModelRequest | None = None
        self._measured: _Measured | None = None
        # Tokens per call at most (spec hito 11, §1.3).
        self.context_budget = context_budget
        # Where the session puts its archive, shared with `recall` (§1.9).
        self._slot = slot if slot is not None else ArchiveSlot()
        # Who summarizes what leaves the window; None: the code's index
        # alone (§1.7).
        self._archivist = archivist
        # How many messages of the conversation, from the start, left the
        # working window, the message that stands for them, and the
        # archivist's index, for the next time (§1.8).
        self._archived = 0
        self._index: Message | None = None
        self._notes: str | None = None
        # The tokens of the prompt of the call in progress, as maha counts
        # them, and, if it goes on from the last call counted, that call's
        # prompt and what was added since: a provider that counts far fewer
        # cut it (decision 14).
        self._sent_tokens = 0
        self._sent_growth: tuple[int, int] | None = None
        # What the session has to save of the archive, in order: each whole
        # output archived, and each time the window was archived (§1.12).
        self._entries: list[ArchiveEntry | OutputEntry] = []

    @property
    def archive(self) -> ContextArchive | None:
        """The session's archive, where a whole output too big for the
        context goes (spec hito 11, §1.6). None: none, and such an output
        is only cut."""
        return self._slot.archive

    @archive.setter
    def archive(self, archive: ContextArchive | None) -> None:
        self._slot.archive = archive

    @property
    def messages(self) -> Sequence[Message]:
        """The whole conversation so far, oldest first, also what left the
        working window."""
        return tuple(self._messages)

    @property
    def working(self) -> Sequence[Message]:
        """What the model gets of the conversation: the index of what was
        archived, and the rest as it is (spec hito 11, §1.8)."""
        return tuple(self._working(()))

    @property
    def archived(self) -> int:
        """How many messages of the conversation, from the start, the index
        stands for."""
        return self._archived

    def restore(self, archived: int, index: Message, notes: str | None) -> None:
        """Start as a resumed session left it: its first `archived`
        messages stand behind `index`, and the archivist's last index was
        `notes` (spec hito 11, §1.12)."""
        self._archived = archived
        self._index = index
        self._notes = notes
        self._measured = None

    def take_entries(self) -> list[ArchiveEntry | OutputEntry]:
        """What the session has to save of the archive since the last time,
        once."""
        entries, self._entries = self._entries, []
        return entries

    def _working(self, turn: Sequence[Message]) -> list[Message]:
        full = [*self._messages, *turn]
        if self._index is None:
            return full
        return [self._index, *full[self._archived :]]

    @property
    def tool_names(self) -> list[str]:
        """The names of the tools the model has, in their order."""
        return self._tools.names()

    async def run(self, text: str) -> AsyncGenerator[AgentEvent]:
        """Run one turn from a user message, yielding what happens.

        The turn is kept when it ends, before `TurnFinished` is yielded, also
        when the user denies a call. If a call to the model fails, or the
        turn is cancelled, what already ran is kept: the turn up to the last
        complete result, and a result for every call of the interrupted step.
        If no tool ran, nothing is kept (spec hito 5, §1.5), unless Ctrl+C
        cut an answer that had begun: its text is kept, marked as
        interrupted (spec hito 6, §1.7).

        The events of each step come from two helpers, read here inside
        `aclosing`: a Ctrl+C or a close at one of their `yield`s closes them
        first and then arrives here, where `_Turn` says what to keep.
        """
        yield TurnStarted(text=text)
        # When the loop stops waiting (spec hito 8, §1.1).
        timeout = self.limits.timeout
        turn = _Turn(
            messages=[Message(role="user", blocks=[TextBlock(text=text)])],
            model=self.model,
            deadline=(
                None if timeout is None else asyncio.get_running_loop().time() + timeout
            ),
        )
        try:
            for turn.step in range(1, self.limits.max_steps + 1):
                if turn.step > 1 and (limit := self._reached(turn.usage, turn.cost)):
                    # Before the call that would pass it; what ran is in the
                    # turn, which the user can go on.
                    self._keep(turn)
                    yield turn.finished(limit, steps=turn.step - 1)
                    return
                async with aclosing(self._archive_if_full(turn)) as events:
                    async for event in events:
                        yield event
                async with aclosing(self._fitting_answer(turn)) as events:
                    async for event in events:
                        yield event
                if turn.no_room:
                    # It did not fit even after archiving: the turn ends.
                    if turn.must_keep:
                        self._keep(turn)
                    yield turn.finished("context_full", steps=turn.step)
                    return
                response, call_cost = self._take_answer(turn)
                yield ModelCallFinished(
                    usage=response.usage, model=response.model, cost=call_cost
                )
                if response.stop_reason == "context_full":
                    # Calling the model again cannot fit either: the turn
                    # ends, and a call it was writing never runs (review of
                    # the deep audit).
                    if turn.calls:
                        blocks = turn.interrupted(CONTEXT_FULL)
                        turn.messages.append(Message(role="tool", blocks=[*blocks]))
                    self._keep(turn)
                    yield turn.finished("context_full", steps=turn.step)
                    return
                if response.stop_reason == "content_filter":
                    # Refused: a call it holds may be cut, and none was
                    # meant to run; the turn ends (audit after hito 10, B1).
                    if turn.calls:
                        refused = [_error(c, REFUSED).result for c in turn.calls]
                        turn.messages.append(Message(role="tool", blocks=[*refused]))
                    self._keep(turn)
                    yield turn.finished("refused", steps=turn.step)
                    return
                if not turn.calls:
                    self._keep(turn)
                    yield turn.finished(_ending(response.stop_reason), steps=turn.step)
                    return
                async with aclosing(
                    self._handle_calls(turn, response.stop_reason)
                ) as events:
                    async for event in events:
                        yield event
                if turn.denied:
                    # Without calling the model again: the user writes next
                    # (spec hito 5, §1.4).
                    self._keep(turn)
                    yield turn.finished("denied", steps=turn.step)
                    return
            # The turn ends on tool results; the user can still go on.
            self._keep(turn)
            yield turn.finished("max_steps", steps=self.limits.max_steps)
        except _TimedOut:
            if turn.failing:
                # The provider kept failing until the limit: that is what
                # happened, not the limit; an eval counts it as the
                # provider's (audit of hito 8; spec hito 8, §12.9). What ran
                # is kept, as after any failed call to the model.
                if turn.must_keep and not turn.kept:
                    self._messages.extend(turn.messages)
                raise turn.failing[0] from None
            self._keep_timed_out(turn)
            if turn.streaming and (paid := self._cut_call(turn)) is not None:
                yield paid
            yield turn.finished(
                "timeout",
                # The call cut while it answered did not end.
                steps=turn.step - 1 if turn.streaming else turn.step,
                answering=turn.streaming,
            )
        except BaseException as exc:
            # A failed call to the model, Ctrl+C or any error nobody expected
            # (spec mejora-2026-10-23-deuda-hito-5, E4). Ctrl+C arrives as
            # CancelledError while the loop waits, or as GeneratorExit when
            # the terminal was the one waiting and closes the loop.
            by_user = isinstance(
                exc, asyncio.CancelledError | GeneratorExit | KeyboardInterrupt
            )
            self._keep_cut(turn, by_user=by_user)
            paid = self._cut_call(turn) if turn.streaming else None
            if paid is not None:
                if by_user:
                    # Nobody reads the events any more: the conversation
                    # takes it (`take_cut_call`).
                    self._unseen_call = paid
                else:
                    yield paid
            raise

    def _cut_call(self, turn: _Turn) -> ModelCallFinished | None:
        """The call in progress, cut: what it used so far, paid all the
        same (audit after hito 10, B2); None if the provider said nothing.
        Counted in the turn once."""
        so_far = turn.accumulator.so_far
        if so_far is None:
            return None
        turn.accumulator.so_far = None
        cut = ModelResponse(
            message=Message(role="assistant", blocks=[]),
            stop_reason="other",
            usage=so_far.usage,
            model=so_far.model,
        )
        call_cost = self._cost(cut, turn.model)
        turn.usage += so_far.usage
        turn.cost = add_cost(turn.cost, call_cost)
        return ModelCallFinished(usage=so_far.usage, model=so_far.model, cost=call_cost)

    def take_cut_call(self) -> ModelCallFinished | None:
        """The call a Ctrl+C cut, which no event could tell, once."""
        paid, self._unseen_call = self._unseen_call, None
        return paid

    def _keep(self, turn: _Turn) -> None:
        """Put the whole turn in the history: it ended."""
        self._messages.extend(turn.messages)
        turn.kept = True

    async def _answer(self, turn: _Turn) -> AsyncGenerator[AgentEvent]:
        """The step's call to the model, with its retries and its fallback,
        gathered in `turn.accumulator`. It yields the retries, the fallback
        and the text as it comes; the fallback answers the rest of the
        turn."""
        turn.accumulator = Accumulator()
        turn.streaming = True
        async with aclosing(
            self._call(turn.messages, turn.model, turn.failing)
        ) as events:
            while True:
                try:
                    event = await _within(anext(events), turn.deadline)
                except StopAsyncIteration:
                    break
                if isinstance(event, ModelRetry | ModelFallback):
                    # The failed try was paid if it got that far.
                    paid = self._cut_call(turn)
                    if paid is not None:
                        yield paid
                    turn.accumulator = Accumulator()
                    if isinstance(event, ModelFallback):
                        turn.model = event.fallback
                    yield event
                    continue
                turn.accumulator.add(event)
                if isinstance(event, TextDelta):
                    yield event
        turn.streaming = False

    async def _fitting_answer(self, turn: _Turn) -> AsyncGenerator[AgentEvent]:
        """The step's answer. If the provider says that the prompt does not
        fit, or answers a prompt it cut in silence, the oldest steps are
        archived, all but the last, and the call is made once more (spec
        hito 11, §1.10, decision 14). `turn.no_room` if it still cannot
        fit."""
        for last in (False, True):
            overflowed = False
            try:
                async with aclosing(self._answer(turn)) as events:
                    async for event in events:
                        yield event
            except ContextOverflowError:
                turn.streaming = False
                overflowed = True
            # Out of the `except`: a Ctrl+C here is not "during" the error.
            if not overflowed:
                if last or not self._overflowed(turn) or not self._can_archive(turn):
                    return
                # The answer of a prompt that did not fit: paid, not kept.
                yield self._discard_answer(turn)
            elif last or not self._can_archive(turn):
                turn.no_room = True
                return
            async with aclosing(self._archive(turn, tail=0)) as events:
                async for event in events:
                    yield event

    def _overflowed(self, turn: _Turn) -> bool:
        """Whether the answer that came says that its prompt did not fit:
        the provider stopped for it, or counted far fewer tokens than were
        sent when they could not fit in the window (it cut them)."""
        try:
            response = turn.accumulator.response()
        except ModelResponseError:
            return False
        if response.stop_reason == "context_full":
            return True
        counted = response.usage.input_tokens
        if counted <= 0:
            # The provider did not count it.
            return False
        window = self._policy(turn.model).window
        sent = self._sent_tokens
        if window is not None and sent > window and counted < sent * SILENT_CUT:
            return True
        if self._sent_growth is None:
            return False
        before, added = self._sent_growth
        return added >= SILENT_GROWTH and counted < before + added * SILENT_SHARE

    def _growth(
        self,
        model: str,
        system: str | None,
        tools: list[ToolSpec],
        messages: Sequence[Message],
    ) -> tuple[int, int] | None:
        """The prompt of the last call counted, and an estimate of what this
        prompt adds to it, if this one goes on from it with the same model
        (another one counts its own way); None if not."""
        measured = self._measured
        if (
            measured is None
            or measured.model != model
            or not measured.matches(system, tools)
        ):
            return None
        for index in range(len(messages) - 1, -1, -1):
            if messages[index] is measured.answer:
                # Its visible text, not its reasoning: that may not go back.
                added = estimate(message_text(_without_reasoning(measured.answer)))
                return measured.prompt, added + estimate_messages(
                    list(messages[index + 1 :])
                )
        return None

    def _discard_answer(self, turn: _Turn) -> ModelCallFinished:
        """Count the answer that came, and leave it out of the turn."""
        response = turn.accumulator.response()
        turn.usage += response.usage
        call_cost = self._cost(response, turn.model)
        turn.cost = add_cost(turn.cost, call_cost)
        turn.accumulator = Accumulator()
        self._measured = None
        return ModelCallFinished(
            usage=response.usage, model=response.model, cost=call_cost
        )

    def _can_archive(self, turn: _Turn) -> bool:
        """Whether some step, besides the last, is still in the window."""
        full = [*self._messages, *turn.messages]
        return archive_cut(full, 0, start=self._archived) > self._archived

    async def _archive_if_full(self, turn: _Turn) -> AsyncGenerator[AgentEvent]:
        """Archive the oldest steps if the next call would pass the ceiling
        (spec hito 11, §1.3): before each call, also in the middle of a
        turn."""
        policy = self._policy(turn.model)
        tokens = self.prompt_tokens(
            self._system_of(turn.model),
            self._tools.specs(),
            self._working(turn.messages),
        )
        if tokens <= policy.ceiling:
            return
        async with aclosing(self._archive(turn, tail=policy.tail)) as events:
            async for event in events:
                yield event

    async def compact(
        self, instructions: str | None = None
    ) -> AsyncGenerator[AgentEvent]:
        """Archive now all but the last steps, also if they fit (`/compact`,
        spec hito 11, §1.11); the person's `instructions` go to the
        archivist. Nothing happens if there is nothing to archive."""
        turn = _Turn(messages=[], model=self.model, deadline=None)
        tail = self._policy(self.model).tail
        async with aclosing(
            self._archive(turn, tail=tail, manual=True, instructions=instructions)
        ) as events:
            async for event in events:
                yield event

    async def _archive(
        self,
        turn: _Turn,
        *,
        tail: int,
        manual: bool = False,
        instructions: str | None = None,
    ) -> AsyncGenerator[AgentEvent]:
        """Move out of the working window the steps before the last ones
        that fit in `tail` tokens (spec hito 11, §1.10). Whole steps, also of
        this turn. Atomic: a Ctrl+C or a failure before the end leaves the
        conversation as it was; what was archived meanwhile is archived
        again with the same ids."""
        full = [*self._messages, *turn.messages]
        cut = archive_cut(full, tail, start=self._archived)
        if cut <= self._archived:
            return
        system, tools = self._system_of(turn.model), self._tools.specs()
        before = self.prompt_tokens(system, tools, self._working(turn.messages))
        yield ContextArchiving(before=before, manual=manual)
        first = self._archived
        leaving = full[first:cut]
        archived = Archived(None)
        if self._archivist is not None:
            archived = await _within(
                self._archivist.archive(
                    leaving,
                    first=first,
                    previous=self._notes,
                    instructions=instructions,
                ),
                turn.deadline,
            )
        cost: Decimal | None = Decimal(0)
        calls = []
        for call in archived.calls:
            turn.usage += call.usage
            turn.cost = add_cost(turn.cost, call.cost)
            cost = add_cost(cost, call.cost)
            calls.append(
                ModelCallFinished(
                    usage=call.usage, model=call.model, cost=call.cost, archivist=True
                )
            )
        notes = archived.notes
        problem = await self._keep_archived(full, first, cut, notes)
        # All at once, after every wait.
        self._notes = notes.index if notes is not None else self._notes
        self._index = archive_index(full[:cut], self._notes)
        self._archived = cut
        self._measured = None
        self._entries.append(
            ArchiveEntry(
                replaces=cut,
                index=self._index,
                manual=manual,
                notes=self._notes,
                summary=notes.summary if notes is not None else None,
            )
        )
        turn.archived = turn.archived or cut > len(self._messages)
        for paid in calls:
            yield paid
        yield ContextArchived(
            before=before,
            after=self.prompt_tokens(system, tools, self._working(turn.messages)),
            steps=len(step_starts(leaving)),
            manual=manual,
            cost=cost,
            notes=notes is not None,
            problem=problem,
        )

    async def _keep_archived(
        self, full: list[Message], first: int, cut: int, notes: ArchiveNotes | None
    ) -> str | None:
        """Put in the archive the messages that leave, and the archivist's
        summary of them; why it could not, if it could not."""
        if self.archive is None:
            return None
        items = archive_items(full, first, cut)
        if notes is not None:
            items.append(summary_item(cut, notes.summary))
        try:
            await self.archive.add(items)
        except ArchiveError as exc:
            return f"archive: {exc}"
        return None

    def _take_answer(self, turn: _Turn) -> tuple[ModelResponse, Decimal | None]:
        """Count the answer that came, put it in the turn and take its tool
        calls as the step's. Returns it, with what it cost."""
        response = turn.accumulator.response()
        turn.usage += response.usage
        call_cost = self._cost(response, turn.model)
        turn.cost = add_cost(turn.cost, call_cost)
        # In the turn before it is told: a turn closed right at
        # ModelCallFinished keeps the answer the person saw (deep
        # audit after hito 9).
        answer = _stamped(response.message, turn.model)
        turn.messages.append(answer)
        self._measure(answer, response.usage)
        turn.calls = [
            b for b in response.message.blocks if isinstance(b, ToolCallBlock)
        ]
        turn.answered = not turn.calls
        # This step's results only: a cut right here must not give
        # its calls the last step's.
        turn.results = []
        return response, call_cost

    async def _handle_calls(
        self, turn: _Turn, stop_reason: StopReason
    ) -> AsyncGenerator[AgentEvent]:
        """The step's tool calls, one by one: proposed, asked about if they
        need it, run, and their results put in the turn."""
        # The block the model was writing when an output limit cut it.
        last = turn.messages[-1].blocks[-1]
        # In order, not in parallel, until hito 17 (spec hito 4, §1.7).
        for call in turn.calls:
            yield ToolCallProposed(call=call)
            if turn.denied:
                # Every call gets a result (spec hito 4, §1.1); these
                # do not run, and do not count as handled.
                skipped = _error(call, NOT_RUN_DENIED)
                turn.results.append(skipped.result)
                yield ToolFinished(
                    call=call,
                    result=skipped.result,
                    summary=skipped.summary,
                    duration=0.0,
                    skipped=True,
                )
                continue
            started = time.monotonic()
            # None: nobody was asked, or the answer was not valid.
            decision: Decision | None = None
            asked = False
            # By the output limit, the last one may be cut even if it looks
            # whole; by a reason maha does not know, only one that is not
            # whole (audit after hito 10, B1, and its review).
            cut = (
                stop_reason == "max_tokens" and (call is last or not _whole(call))
            ) or (stop_reason == "other" and not _whole(call))
            if cut:
                # Cut by the output limit: its error says so, or the
                # model writes the same cut call again (deep audit
                # after hito 9, B1). The last one, also if its arguments
                # look whole: "{}" may be all that came (review).
                prepared: _Ready | _Outcome = _error(call, CUT_BY_OUTPUT)
            else:
                prepared = await _within(self._prepare(call), turn.deadline)
            if isinstance(prepared, _Outcome):
                outcome = prepared
            else:
                question = prepared.request
                if question is not None and self._approvals.covers(question):
                    yield ApprovalCovered(call=call, request=question)
                elif question is not None:
                    yield ApprovalRequested(call=call, request=question)
                    asked = True
                    answer = await self._decide(turn, question)
                    # The time spent deciding is not the tool's.
                    started = time.monotonic()
                    if answer in DECISIONS:
                        decision = answer
                        self._approvals.record(question, decision)
                if asked and decision is None:
                    # Fails closed: a broken gate never runs a call.
                    outcome = _crash(call, f"invalid approval decision: {answer!r}")
                elif decision == "deny":
                    turn.denied = True
                    outcome = _error(call, "the user denied this call")
                elif prepared.tool.waits_for_user:
                    turn.executed = True
                    outcome = await self._wait_for_user(turn, call, prepared)
                else:
                    # Nobody was asked, or "once" or "session".
                    turn.executed = True
                    outcome = await _within(
                        self._run(call, prepared, self._position(turn)), turn.deadline
                    )
            turn.calls_run += 1
            turn.results.append(outcome.result)
            yield ToolFinished(
                call=call,
                result=outcome.result,
                summary=outcome.summary,
                duration=time.monotonic() - started,
                internal_error=outcome.internal_error,
                decision=decision,
            )
        turn.messages.append(Message(role="tool", blocks=list(turn.results)))
        turn.calls = []

    async def _decide(self, turn: _Turn, question: ApprovalRequest) -> object:
        """Ask the gate. The turn's clock stops while the person reads and
        decides (deep audit after hito 9, B4, a decision of the
        maintainer); without a person the answer is at once."""
        answer: object = await _paused(turn, self._gate.decide(question))
        return answer

    async def _wait_for_user(
        self, turn: _Turn, call: ToolCallBlock, ready: _Ready
    ) -> _Outcome:
        """Run a tool that waits for the person (`ask_user`). As while they
        decide on a call, the turn's clock stops: a person reading is no
        slow model (spec hito 10, §1.11)."""
        return await _paused(turn, self._run(call, ready, self._position(turn)))

    def _keep_timed_out(self, turn: _Turn) -> None:
        """What a turn stopped by its time limit keeps: as after Ctrl+C,
        but the turn ends here (spec hito 8, §1.1). A half answer is not
        kept: its mark says the user cut it."""
        if turn.must_keep and not turn.kept:
            if turn.calls:
                blocks = turn.interrupted(TIMED_OUT)
                turn.messages.append(Message(role="tool", blocks=[*blocks]))
            self._messages.extend(turn.messages)

    def _keep_cut(self, turn: _Turn, *, by_user: bool) -> None:
        """What a turn cut by a failed call to the model, by the user or by
        an unexpected error keeps. What ran is kept, so the model does not
        do it again (spec hito 5, §1.5)."""
        # The text the person already saw; a half tool call never ran. A
        # failed model call keeps none: its text may be broken.
        half = turn.accumulator.text if turn.streaming and by_user else ""
        kept = turn.must_keep or half or (turn.answered and by_user)
        if kept and not turn.kept:
            if turn.calls:
                # The model is not called while the calls run: here only
                # Ctrl+C or an unexpected error can cut the step.
                blocks = turn.interrupted(CANCELLED if by_user else INTERRUPTED)
                turn.messages.append(Message(role="tool", blocks=[*blocks]))
            if half:
                turn.messages.append(
                    Message(
                        role="assistant",
                        blocks=[TextBlock(text=half)],
                        interrupted=True,
                    )
                )
            self._messages.extend(turn.messages)

    async def _call(
        self, turn: list[Message], model: str, failing: list[RetryableModelError]
    ) -> AsyncGenerator[ModelEvent | ModelRetry | ModelFallback]:
        """One call to `model`, made again while it fails before its first
        event with an error that may pass, and then once more with the
        fallback, with retries of its own (spec hito 8, §1.14). Once an
        event came, a failure goes up: that answer was already shown.
        `failing` holds the last failure while the call is retried."""
        attempt = 0
        while True:
            began = False
            try:
                request = self._request(turn, model)
                self._sent = request
                async with aclosing(self._client.stream(request)) as events:
                    async for event in events:
                        if not isinstance(event, UsageSoFar):
                            # Only an answer shown cannot be retried: what
                            # was used so far is no answer.
                            began = True
                            failing.clear()
                        yield event
                return
            except RetryableModelError as exc:
                if began:
                    raise
                failing[:] = [exc]
                attempt += 1
                delay = self._retry.delay(attempt, exc.retry_after)
                then: ModelRetry | ModelFallback
                if delay is not None:
                    then = ModelRetry(
                        model=model,
                        attempt=attempt,
                        max_retries=self._retry.max_retries,
                        delay=delay,
                        error=str(exc),
                    )
                elif self.fallback is not None and self.fallback != model:
                    then = ModelFallback(
                        model=model, fallback=self.fallback, error=str(exc)
                    )
                else:
                    raise
            # Out of the `except`: a Ctrl+C here is not "during" the error.
            yield then
            if isinstance(then, ModelFallback):
                model, attempt = then.fallback, 0
            else:
                await self._sleep(then.delay)

    def _reached(
        self, usage: Usage, cost: Decimal | None
    ) -> Literal["max_tokens", "max_cost"] | None:
        """The limit the turn reached with what it spent, if any. A cost
        that is not known reaches the cost limit."""
        limits = self.limits
        tokens = usage.input_tokens + usage.output_tokens
        if limits.max_tokens is not None and tokens >= limits.max_tokens:
            return "max_tokens"
        if limits.max_cost is not None and (cost is None or cost >= limits.max_cost):
            return "max_cost"
        return None

    def _cost(self, response: ModelResponse, model: str) -> Decimal | None:
        return call_cost(response, model, self._catalog, self._provider)

    def _system_of(self, model: str) -> str | None:
        """The system prompt that `model` gets: the session's, with the
        family layer of the fallback if it is another model."""
        if model != self.model and self.system_for is not None:
            return self.system_for(model)
        return self.system

    def _policy(self, model: str) -> ContextPolicy:
        info = self._catalog.get(self._provider, model)
        return ContextPolicy(
            budget=self.context_budget,
            window=info.context if info is not None else None,
        )

    def _request(self, turn: list[Message], model: str) -> ModelRequest:
        info = self._catalog.get(self._provider, model)
        system = self._system_of(model)
        messages = self._working(turn)
        tools = self._tools.specs()
        # What the model may write without passing its window (spec hito
        # 11, §1.4).
        policy = ContextPolicy(window=info.context if info is not None else None)
        self._sent_tokens = self.prompt_tokens(system, tools, messages)
        self._sent_growth = self._growth(model, system, tools, messages)
        max_tokens = policy.answer_room(
            self._sent_tokens, info.max_output if info is not None else None
        )
        return ModelRequest(
            model=model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            effort=self.effort,
        )

    def context_usage(self) -> ContextUsage:
        """What the next call would send, by parts (spec hito 11, §1.11)."""
        info = self._catalog.get(self._provider, self.model)
        policy = ContextPolicy(
            budget=self.context_budget,
            window=info.context if info is not None else None,
        )
        tools = self._tools.specs()
        messages = self._working(())
        results = sum(
            estimate(block.content)
            for message in messages
            for block in message.blocks
            if isinstance(block, ToolResultBlock)
        )
        measured = self._measured
        return ContextUsage(
            budget=policy.budget,
            window=policy.window,
            ceiling=policy.ceiling,
            system=estimate(self.system or ""),
            tools=estimate_tools(tools),
            tool_count=len(tools),
            messages=estimate_messages(list(messages[1:] if self._index else messages)),
            tool_results=results,
            index=estimate(self._index.text) if self._index is not None else 0,
            archived=self._archived,
            total=self.prompt_tokens(self.system, tools, messages),
            exact=measured is not None
            and measured.matches(self.system, tools)
            and any(message is measured.answer for message in messages),
            last_prompt=measured.prompt if measured is not None else None,
            last_cached=measured.cached if measured is not None else None,
        )

    def prompt_tokens(
        self, system: str | None, tools: list[ToolSpec], messages: Sequence[Message]
    ) -> int:
        """The tokens of a prompt: the provider's exact count of the last
        call, if this prompt goes on from it, and an estimate of what came
        after; all estimated if not (spec hito 11, §1.2)."""
        measured = self._measured
        if measured is not None and measured.matches(system, tools):
            for index in range(len(messages) - 1, -1, -1):
                if messages[index] is measured.answer:
                    return measured.tokens + estimate_messages(
                        list(messages[index + 1 :])
                    )
        return (
            estimate(system or "")
            + estimate_tools(tools)
            + estimate_messages(list(messages))
        )

    def _measure(self, answer: Message, usage: Usage) -> None:
        """Keep the exact size of the call that just answered: its prompt
        and its answer, as the provider counted them."""
        sent = self._sent
        tokens = usage.input_tokens + usage.output_tokens
        if sent is None or usage.input_tokens == 0:
            # The provider did not say: the next one is estimated.
            self._measured = None
            return
        self._measured = _Measured(
            model=sent.model,
            answer=answer,
            tokens=tokens,
            prompt=usage.input_tokens,
            cached=usage.cache_read_tokens,
            system=sent.system,
            tools=tuple(sent.tools),
        )

    async def _prepare(self, call: ToolCallBlock) -> _Ready | _Outcome:
        """Find the tool, validate the arguments and ask the tool what to
        ask the user (spec hito 5, §1.2).

        Every failure becomes an error result, and the loop goes on: the
        model can correct itself (spec hito 4, §1.8).
        """
        tool = self._tools.get(call.name)
        if tool is None:
            available = ", ".join(self._tools.names())
            return _error(call, f'unknown tool "{call.name}". Available: {available}')
        arguments = _arguments(call)
        if arguments is None:
            return _error(call, "arguments are not a valid JSON object")
        try:
            params = tool.params.model_validate(arguments)
        except ValidationError as exc:
            return _error(call, f"invalid arguments: {_describe(exc)}")
        try:
            request = await tool.approval(params)
        except ToolError as exc:
            # Before asking: a useless question is not shown.
            return _error(call, str(exc))
        except Exception as exc:
            return _crash(call, f"{type(exc).__name__}: {exc}")
        if tool.permission == "effect" and request is None:
            # An effect always asks: without a request, it does not run.
            return _crash(call, "effect tool without an approval request")
        if request is not None and request.tool != tool.name:
            # The gate decides by the tool the request names: it has to be
            # the one that runs (audit of hito 8).
            return _crash(
                call, f'approval request names "{request.tool}", not "{tool.name}"'
            )
        return _Ready(tool=tool, params=params, request=request)

    def _position(self, turn: _Turn) -> int:
        """Where the step's results go in the conversation."""
        return len(self._messages) + len(turn.messages)

    async def _run(self, call: ToolCallBlock, ready: _Ready, position: int) -> _Outcome:
        """Run an allowed call. Every failure becomes an error result. An
        output too big for the context goes whole to the archive, and the
        model gets its beginning, its end and its id (spec hito 11, §1.6)."""
        try:
            content = await ready.tool.run(ready.params)
        except ToolError as exc:
            return _error(call, str(exc))
        except Exception as exc:
            return _crash(call, f"{type(exc).__name__}: {exc}")
        if not isinstance(content, str):
            # A tool that breaks its contract does not cut the turn (spec
            # mejora-2026-10-26-deuda-pre-hito-6, B3).
            return _crash(call, f"run() returned {type(content).__name__}, not str")
        shown, problem = await self._fit(call, ready.tool.name, content, position)
        result = ToolResultBlock(call_id=call.id, content=shown)
        try:
            # Of the whole output: "4,210 lines" is what the tool gave.
            summary = ready.tool.summary(content)
        except Exception as exc:
            # The tool already ran: the model keeps its real result, and the
            # terminal is told about the bug.
            return _Outcome(
                result=result,
                summary="(no summary)",
                internal_error=f"summary: {type(exc).__name__}: {exc}",
            )
        return _Outcome(result=result, summary=summary, internal_error=problem)

    async def _fit(
        self, call: ToolCallBlock, tool: str, content: str, position: int
    ) -> tuple[str, str | None]:
        """The output as the model gets it, and why it could not be
        archived, if it could not: then it is only cut."""
        if len(content) <= OUTPUT_LIMIT:
            return content, None
        if self.archive is None:
            return fit(content), None
        item = ArchiveItem(
            kind="output", position=position, role="tool", tool=tool, text=content
        )
        try:
            [archived] = await self.archive.add([item])
        except ArchiveError as exc:
            return fit(content), f"archive: {exc}"
        # Whole in the session too: the archive is made again from it.
        self._entries.append(
            OutputEntry(id=archived, position=position, tool=tool, text=content)
        )
        return fit(content, archived_as=archived), None


class _TimedOut(Exception):
    """The turn's time limit passed while the loop waited."""


async def _paused[T](turn: _Turn, waiting: Awaitable[T]) -> T:
    """Wait for `waiting` with the turn's clock stopped: a person is
    reading (deep audit after hito 9, B4)."""
    started = asyncio.get_running_loop().time()
    try:
        return await waiting
    finally:
        if turn.deadline is not None:
            turn.deadline += asyncio.get_running_loop().time() - started


async def _within[T](waiting: Awaitable[T], deadline: float | None) -> T:
    """Wait for `waiting` until `deadline` (the loop's clock), or raise
    `_TimedOut`. Each wait on its own, never across a `yield`: a time limit
    around the whole generator would cancel whoever reads its events."""
    if deadline is None:
        return await waiting
    scope = asyncio.timeout_at(deadline)
    try:
        async with scope:
            return await waiting
    except TimeoutError:
        if scope.expired():
            raise _TimedOut from None
        # Not ours: the awaited code's own.
        raise


@dataclass(frozen=True)
class _Ready:
    """A call that passed validation, with what to ask before running it."""

    tool: Tool[Any]
    params: BaseModel
    request: ApprovalRequest | None


@dataclass(frozen=True)
class _Outcome:
    result: ToolResultBlock
    summary: str
    internal_error: str | None = None


@dataclass(frozen=True)
class _Measured:
    """The last call that answered, as the provider counted it: its
    prompt and its `answer` came to `tokens` (spec hito 11, §1.2)."""

    # The model that answered it, as asked.
    model: str
    answer: Message
    tokens: int
    # Of `tokens`, the prompt's, and of those, the ones read from the cache.
    prompt: int
    cached: int
    system: str | None
    tools: tuple[ToolSpec, ...]

    def matches(self, system: str | None, tools: list[ToolSpec]) -> bool:
        """Whether a prompt with this system and these tools begins as the
        measured one did."""
        return self.system == system and self.tools == tuple(tools)


@dataclass
class _Turn:
    """What one turn holds while it runs. What is kept when the turn is cut
    comes from here."""

    # The turn's messages so far, from the user's.
    messages: list[Message]
    # The model of this turn: the fallback, once it takes over.
    model: str
    # When the loop stops waiting (the loop's clock, spec hito 8, §1.1); it
    # moves on while the person decides on a call.
    deadline: float | None
    usage: Usage = field(default_factory=Usage)
    # None once a call has no price: the turn's cost is then unknown.
    cost: Decimal | None = Decimal(0)
    calls_run: int = 0
    step: int = 0
    # Whether some tool's `run()` was called in this turn.
    executed: bool = False
    # Whether the turn is already in the history.
    kept: bool = False
    # The calls of the current step while they are handled, and their
    # results so far.
    calls: list[ToolCallBlock] = field(default_factory=list)
    results: list[ToolResultBlock] = field(default_factory=list)
    denied: bool = False
    accumulator: Accumulator = field(default_factory=Accumulator)
    # Whether the model is writing the answer of this step.
    streaming: bool = False
    # Whether the turn holds a whole final answer, not yet kept.
    answered: bool = False
    # The provider's last failure while a call is being retried; empty
    # once an answer begins.
    failing: list[RetryableModelError] = field(default_factory=list)
    # Whether steps of this turn left the working window: then the turn is
    # kept however it ends, as the index stands for them (spec hito 11).
    archived: bool = False
    # Whether the prompt did not fit even after archiving.
    no_room: bool = False

    @property
    def must_keep(self) -> bool:
        """Whether the turn is kept even if it is cut: a tool ran, or some
        of its steps were archived."""
        return self.executed or self.archived

    def finished(
        self, reason: TurnEnd, *, steps: int, answering: bool = False
    ) -> TurnFinished:
        return TurnFinished(
            reason=reason,
            usage=self.usage,
            tool_calls=self.calls_run,
            steps=steps,
            cost=self.cost,
            answering=answering,
        )

    def interrupted(self, cause: str) -> list[ToolResultBlock]:
        """The results of the step cut short (see `_interrupted`)."""
        return _interrupted(self.calls, self.results, denied=self.denied, cause=cause)


CUT_BY_OUTPUT = (
    "your answer reached your output limit before this call was complete, "
    "so it was not run; write it again in smaller parts"
)


def _ending(stop_reason: StopReason) -> Literal["end_turn", "max_output", "refused"]:
    """How a turn that ends on an answer without calls ended."""
    if stop_reason == "max_tokens":
        return "max_output"
    if stop_reason == "content_filter":
        return "refused"
    return "end_turn"


def _arguments(call: ToolCallBlock) -> dict[str, Any] | None:
    """Its arguments as a JSON object; None if they are not one. Some
    models send "" for a tool without parameters."""
    try:
        value = json.loads(call.arguments.strip() or "{}")
    except ValueError, RecursionError:
        # RecursionError: nested too deep to parse.
        return None
    return value if isinstance(value, dict) else None


def _whole(call: ToolCallBlock) -> bool:
    """Whether its arguments are a whole JSON object (or none at all)."""
    return _arguments(call) is not None


def _error(
    call: ToolCallBlock, message: str, *, internal_error: str | None = None
) -> _Outcome:
    text = f"error: {message}"
    result = ToolResultBlock(call_id=call.id, content=text, is_error=True)
    return _Outcome(result=result, summary=text, internal_error=internal_error)


def _without_reasoning(message: Message) -> Message:
    blocks = [
        block for block in message.blocks if not isinstance(block, ReasoningBlock)
    ]
    return message.model_copy(update={"blocks": blocks})


def _stamped(message: Message, model: str) -> Message:
    """`message` with the model that wrote its reasoning, as maha asked for
    it: in the OpenAI format only that model gets it back (review of the
    audit after hito 10)."""
    if not any(isinstance(block, ReasoningBlock) for block in message.blocks):
        return message
    blocks = [
        block.model_copy(update={"model": model})
        if isinstance(block, ReasoningBlock)
        else block
        for block in message.blocks
    ]
    return message.model_copy(update={"blocks": blocks})


def _interrupted(
    calls: list[ToolCallBlock],
    results: list[ToolResultBlock],
    *,
    denied: bool,
    cause: str,
) -> list[ToolResultBlock]:
    """The results of a step cut short: the finished calls keep theirs, the
    one in progress gets `cause`, and the rest did not run. Every call keeps
    its result (spec hito 4, §1.1, and spec hito 5, §1.5)."""
    blocks = list(results)
    for index, call in enumerate(calls[len(results) :]):
        if denied:
            message = NOT_RUN_DENIED
        elif index == 0:
            message = cause
        else:
            message = "not run"
        blocks.append(_error(call, message).result)
    return blocks


def _crash(call: ToolCallBlock, detail: str) -> _Outcome:
    """A bug of ours, not of the model: the model gets a generic message,
    and the terminal shows the detail."""
    return _error(call, f'internal error in tool "{call.name}"', internal_error=detail)


def _describe(exc: ValidationError) -> str:
    """Short messages, without echoing the input: "path: Field required"."""
    parts = []
    for error in exc.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in error["loc"]) or "arguments"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)
