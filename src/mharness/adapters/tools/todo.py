"""`todo_write`: the model's task list (spec hito 10, §1.10).

It touches nothing outside `maha`: permission `read`, never asked. The list
lives in the conversation, in the arguments of each call; the terminal
draws it from there.
"""

from mharness.domain.approval import ApprovalRequest
from mharness.domain.todo import TODO_TOOL, TodoList
from mharness.domain.tools import Permission

KEEP_CURRENT = (
    "Keep the list current: update it with the call that starts the next "
    "task, and mark the last tasks completed with your last change."
)


class TodoWrite:
    name = TODO_TOOL
    description = (
        "Your task list, for work of three or more separate changes (never "
        "for one or two edits, nor for a question): the whole list each time, "
        "which replaces the last. Each task is a change to make, never a read "
        "or a check. One task in_progress at a time; send each update in the "
        "same reply as the call that starts the next task, and the last one, "
        "with every finished task completed, with your last change. "
        'Example: {"todos": [{"content": "Rename total in pedidos.py", '
        '"status": "completed"}, {"content": "Update the tests", "status": '
        '"in_progress"}, {"content": "Note it in the CHANGELOG", "status": '
        '"pending"}]}'
    )
    params = TodoList
    permission: Permission = "read"
    waits_for_user = False

    async def approval(self, params: TodoList) -> ApprovalRequest | None:
        return None

    async def run(self, params: TodoList) -> str:
        if not params.unfinished():
            return params.summary()
        # A list left behind misleads whoever reads it: the model is told
        # again, as Claude Code does in its result.
        return f"{params.summary()}\n{KEEP_CURRENT}"

    def summary(self, result: str) -> str:
        return result.splitlines()[0]
