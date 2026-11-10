"""`todo_write`: the model's task list (spec hito 10, §1.10).

It touches nothing outside `maha`: permission `read`, never asked. The list
lives in the conversation, in the arguments of each call; the terminal
draws it from there.
"""

from mharness.domain.approval import ApprovalRequest
from mharness.domain.todo import TodoList
from mharness.domain.tools import Permission


class TodoWrite:
    name = "todo_write"
    description = (
        "Write your task list for work of several steps: the whole list each "
        "time, which replaces the last. Mark a task in_progress before you "
        "start it (one at a time) and completed as soon as it is done. "
        'Example: {"todos": [{"content": "Update the tests", "status": '
        '"in_progress"}, {"content": "Note it in the CHANGELOG", "status": '
        '"pending"}]}'
    )
    params = TodoList
    permission: Permission = "read"

    async def approval(self, params: TodoList) -> ApprovalRequest | None:
        return None

    async def run(self, params: TodoList) -> str:
        return params.summary()

    def summary(self, result: str) -> str:
        return result
