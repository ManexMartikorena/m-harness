"""A `ModelCatalog` in memory (spec hito 7, §1.4)."""

from collections.abc import Iterable

from mharness.domain.catalog import ModelInfo


class MemoryCatalog:
    """Knows exactly the models it is given."""

    def __init__(self, models: Iterable[ModelInfo] = ()) -> None:
        self._models = {(info.provider, info.model): info for info in models}

    def get(self, provider: str, model: str) -> ModelInfo | None:
        return self._models.get((provider, model))

    def models(self) -> list[ModelInfo]:
        return list(self._models.values())
