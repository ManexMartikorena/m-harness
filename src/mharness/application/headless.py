"""One turn without a person, summed up (spec hito 8, §1.3).

`maha -p` and `maha eval` both run their instruction through `run_once()`,
so the evals measure exactly what `-p` does.
"""

import re
import time
from collections.abc import Callable
from contextlib import aclosing
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from mharness.application.sessions import Conversation
from mharness.domain.agent_events import (
    AgentEvent,
    ApprovalRequested,
    ModelCallFinished,
    ToolFinished,
    TurnFinished,
)
from mharness.domain.catalog import add_cost
from mharness.domain.errors import ModelError
from mharness.domain.events import TextDelta
from mharness.domain.model import Usage
from mharness.domain.money import Usd

# How the run ended: as `TurnFinished` says, or `error` if the model failed.
type Reason = Literal[
    "end_turn", "max_steps", "max_cost", "max_tokens", "timeout", "denied", "error"
]


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


# What could pass for the closing tag of the block: any case, spaces, what
# follows the name, and the full-width "<" and "/" (review of the audit of
# hito 8).
_CLOSING = re.compile(r"[<\uff1c]\s*[/\uff0f]\s*(stdin)", re.IGNORECASE)


def instruction(text: str, piped: str | None) -> str:
    """What `maha -p` asks (spec hito 8, §1.10): `text`, and below it what
    was piped, between delimiters, because it is data and not the user's
    words. Without `text`, what was piped is the instruction."""
    if piped is None or not piped.strip():
        return text
    if not text.strip():
        return piped
    # What was piped cannot close its own block (audit of hito 8).
    data = _CLOSING.sub(lambda found: "<\\/" + found.group(1), piped.removesuffix("\n"))
    return f"{text}\n\n<stdin>\n{data}\n</stdin>"


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
    # The text of the call in progress, and of the last one that ended.
    current: list[str] = []
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
        )

    try:
        async with aclosing(conversation.run(text)) as events:
            async for event in events:
                if on_event is not None:
                    on_event(event)
                if isinstance(event, TextDelta):
                    current.append(event.text)
                elif isinstance(event, ModelCallFinished):
                    answer, current = "".join(current), []
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
    except ModelError as exc:
        error = str(exc)
    except Exception as exc:
        raise TurnBroke(summed("error", f"{type(exc).__name__}: {exc}")) from exc
    return summed(reason, error)
