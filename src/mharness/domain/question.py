"""Questions the model asks the person, and their answers (spec hito 10,
§1.11). The schema follows Claude Code's `AskUserQuestion`.

```json
{"questions": [{
  "question": "Which database does the project use?",
  "header": "Database",
  "options": [
    {"label": "SQLite", "description": "A local file"},
    {"label": "PostgreSQL", "description": "A server"}
  ],
  "multi_select": false
}]}
```

The terminal always adds "Other", to write something else: no option may
take that name.
"""

from collections.abc import Sequence

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

ASK_TOOL = "ask_user"
QUESTIONS_MAX = 4
HEADER_MAX = 12
OPTIONS_MIN = 2
OPTIONS_MAX = 4
LABEL_MAX = 60
DESCRIPTION_MAX = 200
QUESTION_MAX = 500
# The choice the terminal adds to every question.
OTHER = "Other"


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("needs some text")
    return text


class Option(BaseModel, frozen=True, extra="forbid"):
    label: str = Field(
        min_length=1, max_length=LABEL_MAX, description="The choice, in 1 to 5 words"
    )
    description: str = Field(
        min_length=1,
        max_length=DESCRIPTION_MAX,
        description="What choosing it means, or what follows from it",
    )

    @field_validator("label")
    @classmethod
    def _label(cls, label: str) -> str:
        _not_blank(label)
        if label.strip().casefold() == OTHER.casefold():
            raise ValueError(f'"{OTHER}" is added by maha: do not offer it')
        return label

    @field_validator("description")
    @classmethod
    def _description(cls, description: str) -> str:
        return _not_blank(description)


class Question(BaseModel, frozen=True, extra="forbid"):
    question: str = Field(
        min_length=1,
        max_length=QUESTION_MAX,
        description="The whole question, ending in a question mark",
    )
    header: str = Field(
        min_length=1,
        max_length=HEADER_MAX,
        description=f"A short tag for it, at most {HEADER_MAX} characters: 'Database'",
    )
    options: list[Option] = Field(
        min_length=OPTIONS_MIN,
        max_length=OPTIONS_MAX,
        description="The real choices; maha adds 'Other' for a free answer",
    )
    multi_select: bool = Field(
        default=False, description="True if several options may be chosen"
    )

    @field_validator("question", "header")
    @classmethod
    def _text(cls, text: str) -> str:
        return _not_blank(text)

    @model_validator(mode="after")
    def _distinct_options(self) -> Question:
        labels = [option.label.strip().casefold() for option in self.options]
        if len(set(labels)) != len(labels):
            raise ValueError("two options have the same label")
        return self


class Questions(BaseModel, frozen=True, extra="forbid"):
    questions: list[Question] = Field(
        min_length=1, max_length=QUESTIONS_MAX, description="1 to 4 questions"
    )

    @model_validator(mode="after")
    def _distinct_questions(self) -> Questions:
        texts = [question.question.strip().casefold() for question in self.questions]
        if len(set(texts)) != len(texts):
            raise ValueError("the same question is asked twice")
        return self


class Answer(BaseModel, frozen=True):
    """What the person chose for one question: labels of its options, or
    their own text for "Other"."""

    header: str
    choices: tuple[str, ...]


def answers_text(answers: Sequence[Answer]) -> str:
    """What the model gets back: `Database: SQLite`, a line per question."""
    return "\n".join(
        f"{answer.header}: {', '.join(answer.choices)}" for answer in answers
    )


def questions_of(arguments: str) -> Questions | None:
    """The questions in a call's arguments; None if they are not valid,
    and so were never shown to the person."""
    try:
        return Questions.model_validate_json(arguments or "{}")
    except ValidationError, RecursionError:
        return None
