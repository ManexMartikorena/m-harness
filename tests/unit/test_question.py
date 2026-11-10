"""The questions of `ask_user` and their answers (spec hito 10, §1.11, and
§4, test 10)."""

from typing import Any

import pytest
from pydantic import ValidationError

from mharness.domain.question import Answer, Questions, answers_text


def option(label: str, description: str = "Una opción") -> dict[str, str]:
    return {"label": label, "description": description}


def question(**changes: Any) -> dict[str, Any]:
    return {
        "question": "¿Qué base de datos usa el proyecto?",
        "header": "Base",
        "options": [option("SQLite"), option("PostgreSQL")],
    } | changes


def test_a_question_with_its_options() -> None:
    asked = Questions.model_validate({"questions": [question()]})

    [one] = asked.questions
    assert (one.header, one.multi_select) == ("Base", False)
    assert [o.label for o in one.options] == ["SQLite", "PostgreSQL"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"questions": []}, "at least 1 item"),
        ({"questions": [question(question=f"¿{n}?") for n in range(5)]}, "at most 4"),
        ({"questions": [question(header="Base de datos SQL")]}, "at most 12"),
        ({"questions": [question(options=[option("SQLite")])]}, "at least 2"),
        (
            {"questions": [question(options=[option(str(n)) for n in range(5)])]},
            "at most 4",
        ),
        ({"questions": [question(options=[option("A"), option("other")])]}, "maha"),
        ({"questions": [question(options=[option("A"), option(" a ")])]}, "same label"),
        ({"questions": [question(header="  ")]}, "needs some text"),
        (
            {"questions": [question(options=[option("A"), option("B", "")])]},
            "at least 1",
        ),
        ({"questions": [question(), question()]}, "asked twice"),
        ({"questions": [question(default="SQLite")]}, "Extra"),
    ],
)
def test_what_breaks_the_schema_is_a_validation_error(
    arguments: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Questions.model_validate(arguments)


def test_the_answers_go_back_a_line_per_question() -> None:
    text = answers_text(
        [
            Answer(header="Base", choices=("SQLite",)),
            Answer(header="Lenguajes", choices=("Python", "Go")),
        ]
    )

    assert text == "Base: SQLite\nLenguajes: Python, Go"
