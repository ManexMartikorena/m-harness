"""The task list in the terminal (spec hito 10, §1.10).

A call to `todo_write` is drawn as the list, in place of its call line:

```
  ☑ Add calcular_iva_reducido
  ▸ Update the tests
  ☐ Note it in the CHANGELOG
```

The tasks come from the model: cleaned as any other text it writes.
"""

from mharness.adapters.cli.text import clean_line
from mharness.domain.agent_events import ToolFinished
from mharness.domain.todo import TODO_TOOL, TodoList, TodoStatus, todo_list

MARKS: dict[TodoStatus, str] = {
    "completed": "☑",
    "in_progress": "▸",
    "pending": "☐",
    "cancelled": "⊘",
}
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
STRIKE = "\x1b[9m"
RESET = "\x1b[0m"
_STYLES: dict[TodoStatus, str] = {
    "completed": DIM,
    "in_progress": BOLD,
    "pending": "",
    "cancelled": DIM + STRIKE,
}


def is_todo(name: str) -> bool:
    """Whether a call is drawn as the list, not as its call line."""
    return name == TODO_TOOL


def todo_lines(todos: TodoList, *, color: bool = False) -> list[str]:
    """A line per task, with its mark."""
    lines = []
    for todo in todos.todos:
        text = clean_line(todo.content)
        style = _STYLES[todo.status] if color else ""
        if style:
            text = f"{style}{text}{RESET}"
        lines.append(f"  {MARKS[todo.status]} {text}")
    return lines


def finished_todo(event: ToolFinished, *, color: bool = False) -> list[str] | None:
    """The list a call to `todo_write` left, or None if the call failed:
    then it is shown as any other call, with its error."""
    if event.result.is_error or not is_todo(event.call.name):
        return None
    todos = todo_list(event.call.arguments)
    return None if todos is None else todo_lines(todos, color=color)
