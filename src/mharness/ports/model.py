"""Port to a language model (DESIGN §6).

Hito 2 asks for the whole answer at once; hito 3 adds streaming.
"""

from typing import Protocol

from mharness.domain.model import ModelRequest, ModelResponse


class ModelClient(Protocol):
    """Anything that can answer a `ModelRequest`.

    Raises a `mharness.domain.errors.ModelError` when the call fails.
    """

    async def complete(self, request: ModelRequest) -> ModelResponse: ...
