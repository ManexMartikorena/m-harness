"""A `ModelClient` that answers from a script (DESIGN §12)."""

from collections.abc import Iterable

from mharness.domain.errors import ModelError
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest, ModelResponse, StopReason, Usage

FAKE_MODEL = "fake-model"


def reply(
    text: str,
    *,
    stop_reason: StopReason = "end_turn",
    usage: Usage | None = None,
) -> ModelResponse:
    """An assistant answer with a single text block."""
    return ModelResponse(
        message=Message(role="assistant", blocks=[TextBlock(text=text)]),
        stop_reason=stop_reason,
        usage=usage or Usage(),
        model=FAKE_MODEL,
    )


class FakeModelClient:
    """Returns the scripted responses in order, or raises the scripted errors.

    Every request received is kept in `requests`. Calling it more times than
    scripted fails the test.
    """

    def __init__(self, script: Iterable[ModelResponse | ModelError]) -> None:
        self._script = list(script)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._script:
            raise AssertionError(
                f"FakeModelClient: script exhausted at call {len(self.requests)}"
            )
        step = self._script.pop(0)
        if isinstance(step, ModelError):
            raise step
        return step
