"""Port to the model catalog (DESIGN §6, spec hito 7, §1.4)."""

from typing import Protocol

from mharness.domain.catalog import ModelInfo


class ModelCatalog(Protocol):
    """What is known of each model: prices, context window, training.

    Read once at start-up, in `bootstrap`: `get` never touches the disk.
    """

    def get(self, provider: str, model: str) -> ModelInfo | None:
        """The model on that provider, or None if the catalog lacks it."""
        ...

    def models(self) -> list[ModelInfo]:
        """Every model of every provider, for `maha models` (spec hito 8,
        §1.15)."""
        ...
