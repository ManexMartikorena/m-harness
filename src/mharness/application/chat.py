"""A conversation with a model, kept in memory (spec hito 2, §1.4).

The model remembers nothing between calls: every `send()` sends the whole
conversation again.
"""

from collections.abc import Sequence

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
        messages = [
            *self._messages,
            Message(role="user", blocks=[TextBlock(text=text)]),
        ]
        # No system prompt until hito 10 (spec hito 2, §1.5).
        response = await self._client.complete(
            ModelRequest(model=self._model, messages=messages)
        )
        self._messages = [*messages, response.message]
        return response
