"""The task list the model keeps while it works (spec hito 10, §1.10).

The whole list goes in every call, as in OpenCode: no ids to keep in step.
The last call of the history is the list, so a resumed session has it back.

```json
{"todos": [
  {"content": "Add calcular_iva_reducido", "status": "completed"},
  {"content": "Update the tests", "status": "in_progress"},
  {"content": "Note it in the CHANGELOG", "status": "pending"}
]}
```
"""

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

# The tool's name: the terminal draws its calls as a list.
TODO_TOOL = "todo_write"

type TodoStatus = Literal["pending", "in_progress", "completed", "cancelled"]

TODO_MAX_TASKS = 50
TODO_MAX_CONTENT = 200

# In the order the summary names them.
_STATUSES: tuple[TodoStatus, ...] = ("completed", "in_progress", "pending", "cancelled")


class Todo(BaseModel, frozen=True, extra="forbid"):
    content: str = Field(
        min_length=1,
        max_length=TODO_MAX_CONTENT,
        description="The task, in a few words, imperative: 'Update the tests'",
    )
    status: TodoStatus = Field(
        description="pending, in_progress (at most one), completed or cancelled"
    )

    @field_validator("content")
    @classmethod
    def _not_blank(cls, content: str) -> str:
        if not content.strip():
            raise ValueError("a task needs some text")
        return content


class TodoList(BaseModel, frozen=True, extra="forbid"):
    todos: list[Todo] = Field(
        min_length=1,
        max_length=TODO_MAX_TASKS,
        description="The whole list, in order, every time: it replaces the last",
    )

    @model_validator(mode="after")
    def _one_at_a_time(self) -> TodoList:
        working = sum(todo.status == "in_progress" for todo in self.todos)
        if working > 1:
            raise ValueError(f"{working} tasks are in_progress: at most one at a time")
        return self

    def summary(self) -> str:
        """`3 tasks: 1 completed, 1 in progress, 1 pending`."""
        total = len(self.todos)
        counts = [
            f"{count} {status.replace('_', ' ')}"
            for status in _STATUSES
            if (count := sum(todo.status == status for todo in self.todos))
        ]
        return f"{total} task{'' if total == 1 else 's'}: {', '.join(counts)}"


def todo_list(arguments: str) -> TodoList | None:
    """The list in a call's arguments; None if they do not hold a valid
    one (the loop answers the model with the error)."""
    try:
        return TodoList.model_validate_json(arguments or "{}")
    except ValidationError, RecursionError:
        return None
