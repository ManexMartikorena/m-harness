"""A conversation with a model, kept in memory (spec hito 2, §1.4).

The model remembers nothing between calls: every `send()` or `stream()` sends
the whole conversation again.
"""

from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing

from mharness.application.collect import Accumulator
from mharness.domain.events import MessageEnd, ModelEvent
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest, ModelResponse
from mharness.ports.model import ModelClient


class Chat:
    def __init__(self, client: ModelClient, *, model: str) -> None:
        self._client = client
        self._model = model
        self._messages: list[Message] = []

    @property
    def messages(self) -> Sequence[Message]:
        """The conversation so far, oldest first."""
        return tuple(self._messages)

    async def send(self, text: str) -> ModelResponse:
        """Send a user message with the whole history and keep the answer.

        If the call fails, the error propagates and the conversation stays as
        it was, so the message can be sent again.
        """
        messages = self._with_user(text)
        response = await self._client.complete(self._request(messages))
        self._messages = [*messages, response.message]
        return response

    async def stream(self, text: str) -> AsyncGenerator[ModelEvent]:
        """Like `send()`, but yield the events as they arrive.

        The turn is kept when `MessageEnd` arrives, before yielding it: it is
        kept even if the caller stops there. If the stream fails or is
        cancelled before, the conversation stays as it was (spec hito 3,
        §1.6).
        """
        messages = self._with_user(text)
        accumulator = Accumulator()
        async with aclosing(self._client.stream(self._request(messages))) as events:
            async for event in events:
                accumulator.add(event)
                if isinstance(event, MessageEnd):
                    self._messages = [*messages, accumulator.response().message]
                yield event

    def _with_user(self, text: str) -> list[Message]:
        """The history plus the new user message, not kept yet."""
        return [*self._messages, Message(role="user", blocks=[TextBlock(text=text)])]

    def _request(self, messages: list[Message]) -> ModelRequest:
        # No system prompt until hito 10 (spec hito 2, §1.5).
        return ModelRequest(model=self._model, messages=messages)
