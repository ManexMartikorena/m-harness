"""The model's questions in the terminal (spec hito 10, §1.11, and §4,
test 10)."""

import io
from typing import Any

from mharness.adapters.cli.questions import TerminalQuestions
from mharness.domain.question import Answer, Question
from tests.fakes.terminal import ScriptedInput


def question(**changes: Any) -> Question:
    return Question.model_validate(
        {
            "question": "¿Qué base de datos usa el proyecto?",
            "header": "Base",
            "options": [
                {"label": "SQLite", "description": "Un fichero local"},
                {"label": "PostgreSQL", "description": "Un servidor"},
            ],
        }
        | changes
    )


async def ask(
    *typed: str, questions: list[Question] | None = None, discard: bool = False
) -> tuple[list[Answer] | None, str]:
    out = io.StringIO()
    person = TerminalQuestions(
        ScriptedInput(*typed), out, discard=(lambda: True) if discard else None
    )
    answers = await person.ask(questions or [question()])
    return answers, out.getvalue()


async def test_the_question_its_options_and_other() -> None:
    answers, out = await ask("2")

    assert out == (
        "  ┌ Base · ¿Qué base de datos usa el proyecto?\n"
        "  │ 1. SQLite — Un fichero local\n"
        "  │ 2. PostgreSQL — Un servidor\n"
        "  │ 3. Other — write your own answer\n"
        "  └ Choose 1-3: "
    )
    assert answers == [Answer(header="Base", choices=("PostgreSQL",))]


async def test_an_option_can_be_named_by_its_label() -> None:
    answers, _ = await ask("  sqlite ")

    assert answers == [Answer(header="Base", choices=("SQLite",))]


async def test_what_names_no_option_asks_again() -> None:
    answers, out = await ask("", "7", "MySQL", "1, 2", "1")

    assert out.count("  └ Choose 1-3: ") == 5
    assert answers == [Answer(header="Base", choices=("SQLite",))]


async def test_other_takes_the_persons_own_answer() -> None:
    answers, out = await ask("3", "", "MariaDB, en un contenedor")

    assert out.endswith("  └ Choose 1-3:   └ Your answer:   └ Your answer: ")
    assert answers == [Answer(header="Base", choices=("MariaDB, en un contenedor",))]


async def test_several_options_with_multi_select() -> None:
    many = question(multi_select=True, header="Bases")

    answers, out = await ask("2, other,1,2", "Redis", questions=[many])

    assert "  └ Choose one or more, separated by commas (1-3): " in out
    # In the order typed, once each; "Other" is the person's text.
    assert answers == [
        Answer(header="Bases", choices=("PostgreSQL", "Redis", "SQLite"))
    ]


async def test_several_questions_are_counted() -> None:
    other = question(question="¿Y la caché?", header="Caché")

    answers, out = await ask("1", "2", questions=[question(), other])

    assert "  ┌ Base (1/2) · ¿Qué base de datos usa el proyecto?\n" in out
    assert "  ┌ Caché (2/2) · ¿Y la caché?\n" in out
    assert answers == [
        Answer(header="Base", choices=("SQLite",)),
        Answer(header="Caché", choices=("PostgreSQL",)),
    ]


async def test_ctrl_d_is_no_answer() -> None:
    # Also after "Other", and in the second question: nothing is half
    # answered.
    assert (await ask())[0] is None
    assert (await ask("3"))[0] is None
    other = question(question="¿Y la caché?", header="Caché")
    assert (await ask("1", questions=[question(), other]))[0] is None


async def test_typed_ahead_input_is_dropped_first() -> None:
    _, out = await ask("1", discard=True)

    assert out.startswith("  (discarded typed input)\n  ┌ Base")


async def test_what_the_model_wrote_cannot_fake_the_screen() -> None:
    tricky = question(
        question="¿Cuál?\x1b[2J",
        options=[
            {"label": "A\nB", "description": "uno\x1b[1A"},
            {"label": "C", "description": "dos"},
        ],
    )

    _, out = await ask("1", questions=[tricky])

    assert "\x1b" not in out
    assert "  │ 1. A" in out
    assert out.count("\n") == 4
