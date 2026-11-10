"""`ask_user`: the model asks the person (spec hito 10, §1.11).

Asking is no effect: permission `read`. The tool knows only the port; the
terminal is wired in `bootstrap.py`. It waits for the person, so the turn's
clock stops meanwhile.
"""

from mharness.domain.approval import ApprovalRequest
from mharness.domain.question import ASK_TOOL, Questions, answers_text
from mharness.domain.tools import Permission, ToolError
from mharness.ports.questions import UserQuestions

NO_ANSWER = "the user did not answer; go on with what you know, or ask in your reply"


class AskUser:
    name = ASK_TOOL
    description = (
        "Ask the user 1 to 4 questions, each with 2 to 4 options; the user "
        "may also write their own answer. Only when you cannot go on without "
        "it and the project does not tell you. "
        'Example: {"questions": [{"question": "Which database does the '
        'project use?", "header": "Database", "options": [{"label": '
        '"SQLite", "description": "A local file"}, {"label": "PostgreSQL", '
        '"description": "A server"}]}]}'
    )
    params = Questions
    permission: Permission = "read"
    waits_for_user = True

    def __init__(self, questions: UserQuestions) -> None:
        self._questions = questions

    async def approval(self, params: Questions) -> ApprovalRequest | None:
        return None

    async def run(self, params: Questions) -> str:
        answers = await self._questions.ask(params.questions)
        if answers is None:
            raise ToolError(NO_ANSWER)
        return answers_text(answers)

    def summary(self, result: str) -> str:
        count = len(result.splitlines())
        return f"{count} answer{'' if count == 1 else 's'}"
