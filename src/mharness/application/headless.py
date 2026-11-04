"""One turn without a person, summed up (spec hito 8, §1.3).

`maha -p` and `maha eval` both run their instruction through `run_once()`,
so the evals measure exactly what `-p` does.
"""

import secrets
import time
from collections.abc import Callable
from contextlib import aclosing
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from mharness.application.collect import Accumulator
from mharness.application.sessions import Conversation
from mharness.domain.agent_events import (
    AgentEvent,
    ApprovalRequested,
    ModelCallFinished,
    ToolFinished,
    TurnFinished,
)
from mharness.domain.catalog import add_cost
from mharness.domain.errors import (
    ModelAuthError,
    ModelError,
    ModelRequestError,
    RetryableModelError,
)
from mharness.domain.events import TextDelta
from mharness.domain.model import Usage
from mharness.domain.money import Usd

# How the run ended: as `TurnFinished` says, or `error` if the model failed.
type Reason = Literal[
    "end_turn",
    "max_steps",
    "max_cost",
    "max_tokens",
    "timeout",
    "denied",
    "max_output",
    "refused",
    "context_full",
    "error",
]
# Whose the model's failure is: `provider`, one that may pass if repeated
# (429, 5xx, network); `credentials`, a rejected key; `request`, a request
# the provider rejected (another 4xx: maha built it wrong, or the model is
# unknown); `response`, an answer maha cannot read. The evals count the
# last two as failures: they may be a bug of maha (deep audit, I2).
type Failure = Literal["provider", "credentials", "request", "response"]


class RunResult(BaseModel, frozen=True):
    # None if the run kept nothing: there is no session to resume (audit of
    # hito 8).
    session: str | None
    # The id of its trace, if it has one: where `maha trace` finds what
    # happened, also in a run that kept nothing (review of the audit of
    # hito 8).
    trace: str | None
    # The final answer: the text of the last call to the model.
    text: str
    reason: Reason
    # Calls to the model.
    steps: int
    tool_calls: int
    # Results that failed, but not the denied nor the skipped ones.
    tool_errors: int
    # The title of each request that was denied.
    denials: list[str]
    usage: Usage
    # None if a call has no known cost.
    cost: Usd | None
    # Seconds of the clock.
    duration: float
    # The one that answered last.
    model: str
    # What the model's failure said, if it failed.
    error: str | None
    # Whose that failure is, if it failed.
    failure: Failure | None = None


def instruction(text: str, piped: str | None, *, tag: str | None = None) -> str:
    """What `maha -p` asks (spec hito 8, §1.10): `text`, and below it what
    was piped, between delimiters, because it is data and not the user's
    words. Without `text`, what was piped is the instruction.

    The tag carries a random value of this run: the piped text cannot know
    it, so it cannot close its own block. Escaping look-alikes of
    `</stdin>` always left some out (audits of hito 8 and after hito 9,
    B5)."""
    if piped is None or not piped.strip():
        return text
    if not text.strip():
        return piped
    tag = tag or f"stdin-{secrets.token_hex(8)}"
    return f"{text}\n\n<{tag}>\n{piped.removesuffix('\n')}\n</{tag}>"


class TurnBroke(Exception):
    """A bug, or the disk failing, in the middle of a turn. `result` is what
    the turn ran and spent until then (review of the audit of hito 8)."""

    def __init__(self, result: RunResult) -> None:
        super().__init__(result.error)
        self.result = result


async def run_once(
    conversation: Conversation,
    text: str,
    on_event: Callable[[AgentEvent], None] | None = None,
) -> RunResult:
    """Run one turn of `conversation` with `text` and sum it up; `on_event`
    sees each event as it comes. A failed call to the model is an `error`
    result, with what the turn kept saved; anything else that fails is a
    bug, and goes up as `TurnBroke`, with what the turn spent."""
    started = time.monotonic()
    # The text of the call in progress, and of the last one that ended;
    # joined by blocks as the session keeps it, so that two paragraphs do
    # not run together (review of the deep audit).
    current = Accumulator()
    answer = ""
    steps = 0
    usage = Usage()
    cost: Decimal | None = Decimal(0)
    model = conversation.model
    asked: dict[str, str] = {}
    denials: list[str] = []
    tool_errors = 0
    tool_calls = 0
    reason: Reason = "error"
    error: str | None = None

    failure: Failure | None = None

    def summed(reason: Reason, error: str | None) -> RunResult:
        return RunResult(
            session=conversation.id if conversation.stored else None,
            trace=conversation.id if conversation.exists else None,
            text=answer,
            reason=reason,
            steps=steps,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
            denials=denials,
            usage=usage,
            cost=cost,
            duration=time.monotonic() - started,
            model=model,
            error=error,
            failure=failure,
        )

    try:
        async with aclosing(conversation.run(text)) as events:
            async for event in events:
                if on_event is not None:
                    on_event(event)
                if isinstance(event, TextDelta):
                    current.add(event)
                elif isinstance(event, ModelCallFinished):
                    answer, current = current.text, Accumulator()
                    steps += 1
                    usage += event.usage
                    cost = add_cost(cost, event.cost)
                    model = event.model
                elif isinstance(event, ApprovalRequested):
                    asked[event.call.id] = event.request.title
                elif isinstance(event, ToolFinished):
                    # As the loop counts them: the skipped ones are not.
                    tool_calls += not event.skipped
                    if event.decision == "deny":
                        denials.append(asked.get(event.call.id, event.call.name))
                    elif event.result.is_error and not event.skipped:
                        tool_errors += 1
                elif isinstance(event, TurnFinished):
                    reason = event.reason
                    if event.answering:
                        # The last step is the one cut: the text of the one
                        # before ("let me read it") is no answer, as after a
                        # failed call (review of the deep audit).
                        answer = ""
    except ModelError as exc:
        error = str(exc)
        # The turn gave no final answer: the text of a step before ("let me
        # read it") is not one (deep audit after hito 9, I11).
        answer = ""
        failure = failure_of(exc)
    except Exception as exc:
        raise TurnBroke(summed("error", f"{type(exc).__name__}: {exc}")) from exc
    return summed(reason, error)


def failure_of(error: ModelError) -> Failure:
    """Whose a failed call is (deep audit, I2). One of no known kind is
    taken as maha's answer problem, not the provider's: an eval must not
    hide it."""
    if isinstance(error, RetryableModelError):
        return "provider"
    if isinstance(error, ModelAuthError):
        return "credentials"
    if isinstance(error, ModelRequestError):
        return "request"
    return "response"
