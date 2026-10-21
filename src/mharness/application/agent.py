"""The agent loop: call the model, run the tools it asks for, repeat
(DESIGN §4, spec hito 4, §1.7).

The model only proposes calls; this code validates and runs them.
"""

import json
import time
from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from dataclasses import dataclass

from pydantic import ValidationError

from mharness.application.collect import Accumulator
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import (
    AgentEvent,
    ModelCallFinished,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
)
from mharness.domain.events import TextDelta
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import ModelRequest, Usage
from mharness.domain.tools import ToolError
from mharness.ports.model import ModelClient

# Calls to the model in one turn. A limit in code, not in the prompt.
MAX_STEPS = 25


class Agent:
    """A conversation with a model that can use tools, kept in memory.

    Every step sends the whole history, the turn so far and the tools.
    """

    def __init__(
        self,
        client: ModelClient,
        tools: ToolRegistry,
        *,
        model: str,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._client = client
        self._tools = tools
        self._model = model
        self._max_steps = max_steps
        self._messages: list[Message] = []

    @property
    def messages(self) -> Sequence[Message]:
        """The conversation so far, oldest first."""
        return tuple(self._messages)

    async def run(self, text: str) -> AsyncGenerator[AgentEvent]:
        """Run one turn from a user message, yielding what happens.

        The turn is kept when it ends, before `TurnFinished` is yielded. If a
        call to the model fails, or the turn is cancelled, nothing is kept:
        no tool has an effect yet (spec hito 4, §1.7).
        """
        turn = [Message(role="user", blocks=[TextBlock(text=text)])]
        usage = Usage()
        calls_run = 0
        for _ in range(self._max_steps):
            accumulator = Accumulator()
            request = self._request(turn)
            async with aclosing(self._client.stream(request)) as events:
                async for event in events:
                    accumulator.add(event)
                    if isinstance(event, TextDelta):
                        yield event
            response = accumulator.response()
            usage = _add(usage, response.usage)
            yield ModelCallFinished(usage=response.usage, model=response.model)
            turn.append(response.message)
            calls = [b for b in response.message.blocks if isinstance(b, ToolCallBlock)]
            if not calls:
                self._messages.extend(turn)
                yield TurnFinished(reason="end_turn", usage=usage, tool_calls=calls_run)
                return
            results: list[ToolResultBlock] = []
            # In order, not in parallel, until hito 15 (spec hito 4, §1.7).
            for call in calls:
                yield ToolCallProposed(call=call)
                started = time.monotonic()
                outcome = await self._execute(call)
                calls_run += 1
                results.append(outcome.result)
                yield ToolFinished(
                    call=call,
                    result=outcome.result,
                    summary=outcome.summary,
                    duration=time.monotonic() - started,
                    internal_error=outcome.internal_error,
                )
            turn.append(Message(role="tool", blocks=list(results)))
        # The turn ends on tool results; the user can still go on.
        self._messages.extend(turn)
        yield TurnFinished(reason="max_steps", usage=usage, tool_calls=calls_run)

    def _request(self, turn: list[Message]) -> ModelRequest:
        # No system prompt until hito 10 (spec hito 2, §1.5).
        return ModelRequest(
            model=self._model,
            messages=[*self._messages, *turn],
            tools=self._tools.specs(),
        )

    async def _execute(self, call: ToolCallBlock) -> _Outcome:
        """Validate the arguments and run the tool.

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
        except ValueError:
            arguments = None
        if not isinstance(arguments, dict):
            return _error(call, "arguments are not a valid JSON object")
        try:
            params = tool.params.model_validate(arguments)
        except ValidationError as exc:
            return _error(call, f"invalid arguments: {_describe(exc)}")
        try:
            content = await tool.run(params)
        except ToolError as exc:
            return _error(call, str(exc))
        except Exception as exc:
            # A bug of ours, not of the model: the model gets a generic
            # message, and the terminal shows the exception.
            return _error(
                call,
                f'internal error in tool "{call.name}"',
                internal_error=f"{type(exc).__name__}: {exc}",
            )
        result = ToolResultBlock(call_id=call.id, content=content)
        return _Outcome(result=result, summary=tool.summary(content))


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


def _describe(exc: ValidationError) -> str:
    """Short messages, without echoing the input: "path: Field required"."""
    parts = []
    for error in exc.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in error["loc"]) or "arguments"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


def _add(total: Usage, more: Usage) -> Usage:
    return Usage(
        input_tokens=total.input_tokens + more.input_tokens,
        output_tokens=total.output_tokens + more.output_tokens,
        cache_read_tokens=total.cache_read_tokens + more.cache_read_tokens,
        cache_write_tokens=total.cache_write_tokens + more.cache_write_tokens,
    )
