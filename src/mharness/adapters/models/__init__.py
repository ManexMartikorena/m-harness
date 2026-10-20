"""Model adapters: one per API format (DESIGN §8)."""

from mharness.adapters.models.openai_chat import OpenAIChatClient

__all__ = ["OpenAIChatClient"]
