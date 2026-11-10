"""The titles of the sessions (spec hito 10, §1.12).

After the first turn of a conversation, the small model names it from its
first message, in the background: nobody waits for it. If it fails, the
session keeps the first line of that message as its title.

```
20261110-095030-e31b  2026-11-10 10:50  4 messages  ~/tienda  Arreglar el IVA reducido
```
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from mharness.application.agent import call_cost
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest, Usage
from mharness.domain.prompt import render
from mharness.domain.session import clean_title
from mharness.ports.catalog import ModelCatalog
from mharness.ports.model import ModelClient

# What the small model reads of the first message (as OpenCode, §1.0).
MESSAGE_MAX = 2000
# A title is a few words; a model that reasons needs room before them.
TITLE_TOKENS = 1024


def small_model(
    configured: str | None, catalog: ModelCatalog, provider: str, session: str
) -> str:
    """The model of the titles: the configured one; if none, the one the
    catalog gives the provider; if neither, the session's own."""
    return configured or catalog.small_model(provider) or session


@dataclass(frozen=True)
class Title:
    """A title the small model wrote, and what writing it cost."""

    # None if it wrote nothing usable: the call was paid all the same.
    text: str | None
    model: str
    usage: Usage
    # None if neither the provider nor the catalog gives a price.
    cost: Decimal | None


class Titler:
    """Asks the small model for a session's title."""

    def __init__(
        self,
        client: ModelClient,
        *,
        model: str,
        template: str,
        catalog: ModelCatalog,
        provider: str,
        failed: Callable[[str], None] = lambda kind: None,
    ) -> None:
        self.model = model
        self._client = client
        self._template = template
        self._catalog = catalog
        self._provider = provider
        # Told the kind of each failure, for maha.log: never its message,
        # which may hold what the person wrote.
        self._failed = failed

    async def title(self, first: str) -> Title | None:
        """The title of a conversation that starts with `first`; None if
        the call failed: the session keeps its first line as its title."""
        text = render(self._template, {"message": first[:MESSAGE_MAX]})
        request = ModelRequest(
            model=self.model,
            messages=[Message(role="user", blocks=[TextBlock(text=text)])],
            max_tokens=TITLE_TOKENS,
        )
        try:
            response = await self._client.complete(request)
        except Exception as exc:
            # A title is never worth an error on screen.
            self._failed(type(exc).__name__)
            return None
        cost = call_cost(response, self.model, self._catalog, self._provider)
        return Title(
            text=clean_title(response.message.text),
            model=self.model,
            usage=response.usage,
            cost=cost,
        )
