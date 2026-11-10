"""The titles of the sessions (spec hito 10, §1.12)."""

from mharness.ports.catalog import ModelCatalog


def small_model(
    configured: str | None, catalog: ModelCatalog, provider: str, session: str
) -> str:
    """The model of the titles: the configured one; if none, the one the
    catalog gives the provider; if neither, the session's own."""
    return configured or catalog.small_model(provider) or session
