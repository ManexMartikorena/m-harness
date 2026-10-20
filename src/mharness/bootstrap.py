"""Composition root: the only module that knows every piece.

It reads the configuration, builds the adapters, injects them into the
application and starts the `maha` command.
"""

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

from mharness import config
from mharness.adapters import cli
from mharness.adapters.models import OpenAIChatClient
from mharness.application.chat import Chat


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the `maha` command."""
    options = cli.parse(argv)
    if isinstance(options, int):
        return options
    try:
        settings = config.load(cwd=Path.cwd(), env=os.environ)
    except config.ConfigError as exc:
        return cli.fail(str(exc))
    return asyncio.run(_converse(settings))


async def _converse(settings: config.Settings) -> int:
    provider = settings.provider
    async with OpenAIChatClient(
        base_url=provider.base_url,
        api_key=settings.api_key,
        session_header=provider.session_header,
    ) as client:
        chat = Chat(client, model=settings.model)
        return await cli.converse(
            chat, provider=settings.provider_name, model=settings.model
        )
