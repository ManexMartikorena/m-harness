"""Port to a language model (DESIGN §6).

`complete()` gives the whole answer at once; `stream()` gives it as it
arrives (spec hito 3, §1.2).
"""

from collections.abc import AsyncGenerator
from typing import Protocol

from mharness.domain.events import ModelEvent
from mharness.domain.model import ModelRequest, ModelResponse


class ModelClient(Protocol):
    """Anything that can answer a `ModelRequest`.

    Raises a `mharness.domain.errors.ModelError` when the call fails.
    """

    async def complete(self, request: ModelRequest) -> ModelResponse: ...

    # `def`, not `async def`: an async generator returns the iterator itself,
    # not a coroutine. An `AsyncGenerator` can be closed with `aclose()`.
    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelEvent]:
        """Yield `TextDelta`s and, last, one `MessageEnd`."""
        ...
