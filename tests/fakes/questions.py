"""A person for tests: answers the model's questions from a script (spec
hito 10, §1.11)."""

from collections.abc import Sequence

from mharness.domain.question import Answer, Question


class FakePerson:
    """Gives `answers` to every call to `ask`, and keeps what was asked."""

    def __init__(self, answers: list[Answer] | None = None) -> None:
        self.answers = answers
        self.asked: list[Sequence[Question]] = []

    async def ask(self, questions: Sequence[Question]) -> list[Answer] | None:
        self.asked.append(questions)
        return self.answers
