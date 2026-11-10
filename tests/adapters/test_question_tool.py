"""`ask_user` over a fake person (spec hito 10, §1.11)."""

import pytest

from mharness.adapters.tools.question import NO_ANSWER, AskUser
from mharness.domain.question import Answer, Questions
from mharness.domain.tools import ToolError
from mharness.ports.questions import UserQuestions
from mharness.ports.tools import Tool
from tests.fakes.questions import FakePerson

ASKED = Questions.model_validate(
    {
        "questions": [
            {
                "question": "¿Qué base de datos?",
                "header": "Base",
                "options": [
                    {"label": "SQLite", "description": "Un fichero"},
                    {"label": "PostgreSQL", "description": "Un servidor"},
                ],
            }
        ]
    }
)


def test_ask_user_satisfies_the_ports() -> None:
    person: UserQuestions = FakePerson([])
    tool: Tool[Questions] = AskUser(person)

    assert (tool.name, tool.permission, tool.waits_for_user) == (
        "ask_user",
        "read",
        True,
    )


async def test_it_never_asks_permission_and_returns_the_answers() -> None:
    person = FakePerson([Answer(header="Base", choices=("SQLite",))])
    tool = AskUser(person)

    assert await tool.approval(ASKED) is None
    result = await tool.run(ASKED)

    assert result == "Base: SQLite"
    assert person.asked == [ASKED.questions]
    assert tool.summary(result) == "1 answer"


async def test_no_answer_is_an_error_for_the_model() -> None:
    with pytest.raises(ToolError, match=NO_ANSWER):
        await AskUser(FakePerson(None)).run(ASKED)
