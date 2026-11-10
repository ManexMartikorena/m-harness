"""Port to the person who answers the model's questions (spec hito 10,
§1.11). The terminal implements it; without a person, nothing does, and
`ask_user` is not registered."""

from collections.abc import Sequence
from typing import Protocol

from mharness.domain.question import Answer, Question


class UserQuestions(Protocol):
    async def ask(self, questions: Sequence[Question]) -> list[Answer] | None:
        """An answer per question, in their order; None if the person
        gave none (Ctrl+D)."""
        ...
