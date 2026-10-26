"""The agent loop: call the model, run the tools it asks for, repeat
(DESIGN §4, spec hito 4, §1.7, and spec hito 5, §1.4).

The model only proposes calls; this code validates them, asks the user when
the tool needs it, and runs them.
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from mharness.application.approvals import SessionApprovals
from mharness.application.collect import Accumulator
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import (
    AgentEvent,
    ApprovalRequested,
    ModelCallFinished,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
)
from mharness.domain.approval import ApprovalRequest, Decision
from mharness.domain.events import TextDelta
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import ModelRequest, Usage
from mharness.domain.tools import ToolError
from mharness.ports.approval import ApprovalGate
from mharness.ports.model import ModelClient
from mharness.ports.tools import Tool

# Calls to the model in one turn. A limit in code, not in the prompt.
MAX_STEPS = 25

NOT_RUN_DENIED = "not run: a previous call was denied"
# What the call in progress gets when its step is cut short.
CANCELLED = "cancelled by the user"
INTERRUPTED = "interrupted by an internal error"

# The only answers that run a call that asked, or deny it.
DECISIONS: tuple[Decision, ...] = ("once", "session", "deny")


class Agent:
    """A conversation with a model that can use tools, kept in memory.

    Every step sends the whole history, the turn so far and the tools. The
    `gate` decides on the calls that need approval; what the user approves
    for the whole session lives as long as the agent.
    """

    def __init__(
        self,
        client: ModelClient,
        tools: ToolRegistry,
        *,
        gate: ApprovalGate,
        model: str,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._client = client
        self._tools = tools
        self._gate = gate
        self._approvals = SessionApprovals()
        self._model = model
        self._max_steps = max_steps
        self._messages: list[Message] = []

    @property
    def messages(self) -> Sequence[Message]:
        """The conversation so far, oldest first."""
        return tuple(self._messages)

    async def run(self, text: str) -> AsyncGenerator[AgentEvent]:
        """Run one turn from a user message, yielding what happens.

        The turn is kept when it ends, before `TurnFinished` is yielded, also
        when the user denies a call. If a call to the model fails, or the
        turn is cancelled, what already ran is kept: the turn up to the last
        complete result, and a result for every call of the interrupted step.
        If no tool ran, nothing is kept (spec hito 5, §1.5), unless Ctrl+C
        cut an answer that had begun: its text is kept, marked as
        interrupted (spec hito 6, §1.7).
        """
        turn = [Message(role="user", blocks=[TextBlock(text=text)])]
        usage = Usage()
        calls_run = 0
        # Whether some tool's `run()` was called in this turn.
        executed = False
        # Whether the turn is already in the history.
        kept = False
        # The calls of the current step while they are handled, and their
        # results so far.
        calls: list[ToolCallBlock] = []
        results: list[ToolResultBlock] = []
        denied = False
        accumulator = Accumulator()
        # Whether the model is writing the answer of this step.
        streaming = False
        try:
            for step in range(1, self._max_steps + 1):
                accumulator = Accumulator()
                request = self._request(turn)
                streaming = True
                async with aclosing(self._client.stream(request)) as events:
                    async for event in events:
                        accumulator.add(event)
                        if isinstance(event, TextDelta):
                            yield event
                streaming = False
                response = accumulator.response()
                usage += response.usage
                yield ModelCallFinished(usage=response.usage, model=response.model)
                turn.append(response.message)
                calls = [
                    b for b in response.message.blocks if isinstance(b, ToolCallBlock)
                ]
                if not calls:
                    self._messages.extend(turn)
                    kept = True
                    yield TurnFinished(
                        reason="end_turn",
                        usage=usage,
                        tool_calls=calls_run,
                        steps=step,
                    )
                    return
                results = []
                # In order, not in parallel, until hito 15 (spec hito 4, §1.7).
                for call in calls:
                    yield ToolCallProposed(call=call)
                    if denied:
                        # Every call gets a result (spec hito 4, §1.1); these
                        # do not run, and do not count as handled.
                        skipped = _error(call, NOT_RUN_DENIED)
                        results.append(skipped.result)
                        yield ToolFinished(
                            call=call,
                            result=skipped.result,
                            summary=skipped.summary,
                            duration=0.0,
                        )
                        continue
                    started = time.monotonic()
                    # None: nobody was asked, or the answer was not valid.
                    decision: Decision | None = None
                    asked = False
                    prepared = await self._prepare(call)
                    if isinstance(prepared, _Outcome):
                        outcome = prepared
                    else:
                        question = prepared.request
                        if question is not None and not self._approvals.covers(
                            question
                        ):
                            yield ApprovalRequested(call=call, request=question)
                            asked = True
                            answer: object = await self._gate.decide(question)
                            # The time spent deciding is not the tool's.
                            started = time.monotonic()
                            if answer in DECISIONS:
                                decision = answer
                                self._approvals.record(question, decision)
                        if asked and decision is None:
                            # Fails closed: a broken gate never runs a call.
                            outcome = _crash(
                                call, f"invalid approval decision: {answer!r}"
                            )
                        elif decision == "deny":
                            denied = True
                            outcome = _error(call, "the user denied this call")
                        else:
                            # Nobody was asked, or "once" or "session".
                            executed = True
                            outcome = await self._run(call, prepared)
                    calls_run += 1
                    results.append(outcome.result)
                    yield ToolFinished(
                        call=call,
                        result=outcome.result,
                        summary=outcome.summary,
                        duration=time.monotonic() - started,
                        internal_error=outcome.internal_error,
                        decision=decision,
                    )
                turn.append(Message(role="tool", blocks=list(results)))
                calls = []
                if denied:
                    # Without calling the model again: the user writes next
                    # (spec hito 5, §1.4).
                    self._messages.extend(turn)
                    kept = True
                    yield TurnFinished(
                        reason="denied", usage=usage, tool_calls=calls_run, steps=step
                    )
                    return
            # The turn ends on tool results; the user can still go on.
            self._messages.extend(turn)
            kept = True
            yield TurnFinished(
                reason="max_steps",
                usage=usage,
                tool_calls=calls_run,
                steps=self._max_steps,
            )
        except BaseException as exc:
            # A failed call to the model, Ctrl+C or any error nobody expected
            # (spec mejora-2026-10-23-deuda-hito-5, E4). Ctrl+C arrives as
            # CancelledError while the loop waits, or as GeneratorExit when
            # the terminal was the one waiting and closes the loop. What ran
            # is kept, so the model does not do it again (spec hito 5, §1.5).
            by_user = isinstance(exc, asyncio.CancelledError | GeneratorExit)
            # The text the person already saw; a half tool call never ran. A
            # failed model call keeps none: its text may be broken.
            half = accumulator.text if streaming and by_user else ""
            if (executed or half) and not kept:
                if calls:
                    # The model is not called while the calls run: here only
                    # Ctrl+C or an unexpected error can cut the step.
                    cause = CANCELLED if by_user else INTERRUPTED
                    blocks = _interrupted(calls, results, denied=denied, cause=cause)
                    turn.append(Message(role="tool", blocks=[*blocks]))
                if half:
                    turn.append(
                        Message(
                            role="assistant",
                            blocks=[TextBlock(text=half)],
                            interrupted=True,
                        )
                    )
                self._messages.extend(turn)
            raise

    def _request(self, turn: list[Message]) -> ModelRequest:
        # No system prompt until hito 10 (spec hito 2, §1.5).
        return ModelRequest(
            model=self._model,
            messages=[*self._messages, *turn],
            tools=self._tools.specs(),
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
        try:
            # Some models send "" for a tool without parameters.
            arguments = json.loads(call.arguments.strip() or "{}")
        except ValueError, RecursionError:
            # RecursionError: nested too deep to parse.
            arguments = None
        if not isinstance(arguments, dict):
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
        return _Ready(tool=tool, params=params, request=request)

    async def _run(self, call: ToolCallBlock, ready: _Ready) -> _Outcome:
        """Run an allowed call. Every failure becomes an error result."""
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
        result = ToolResultBlock(call_id=call.id, content=content)
        try:
            summary = ready.tool.summary(content)
        except Exception as exc:
            # The tool already ran: the model keeps its real result, and the
            # terminal is told about the bug.
            return _Outcome(
                result=result,
                summary="(no summary)",
                internal_error=f"summary: {type(exc).__name__}: {exc}",
            )
        return _Outcome(result=result, summary=summary)


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


def _error(
    call: ToolCallBlock, message: str, *, internal_error: str | None = None
) -> _Outcome:
    text = f"error: {message}"
    result = ToolResultBlock(call_id=call.id, content=text, is_error=True)
    return _Outcome(result=result, summary=text, internal_error=internal_error)


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
