"""One `ModelClient` per API format, chosen for each request (spec hito 9,
§1.2).

`/model` and the fallback model may change the format in the middle of a
session, so one client per session is not enough: the router sends each
request to the client of its model's format.
"""

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import aclosing
from typing import get_args

from mharness.domain.catalog import SpokenApi
from mharness.domain.errors import ModelRequestError
from mharness.domain.events import ModelEvent
from mharness.domain.model import ModelRequest, ModelResponse
from mharness.ports.model import ModelClient

_SPOKEN = get_args(SpokenApi.__value__)


class ModelRouter:
    """A `ModelClient` that hands each request to the client of its model's
    format. `api_of` says the format of a model; `clients` has one client
    per format the provider serves."""

    def __init__(
        self, clients: Mapping[str, ModelClient], api_of: Callable[[str], str]
    ) -> None:
        self._clients = dict(clients)
        self._api_of = api_of

    async def complete(self, request: ModelRequest) -> ModelResponse:
        return await self._client(request.model).complete(request)

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelEvent]:
        client = self._client(request.model)
        async with aclosing(client.stream(request)) as events:
            async for event in events:
                yield event

    def _client(self, model: str) -> ModelClient:
        """The client of `model`'s format. Raises `ModelRequestError`
        before any call if there is none: a 400 from the provider would
        not say why."""
        api = self._api_of(model)
        client = self._clients.get(api)
        if client is not None:
            return client
        if api in _SPOKEN:
            reason = "which this provider does not serve"
        else:
            reason = "which maha does not speak yet"
        raise ModelRequestError(f"{model} uses the {api} API, {reason}")
