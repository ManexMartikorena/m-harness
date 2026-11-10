"""`todo_write` (spec hito 10, §1.10)."""

from mharness.adapters.tools import TodoWrite
from mharness.adapters.tools.todo import KEEP_CURRENT
from mharness.domain.todo import TodoList
from mharness.ports.tools import Tool


def test_todo_write_satisfies_the_port() -> None:
    tool: Tool[TodoList] = TodoWrite()

    assert (tool.name, tool.permission) == ("todo_write", "read")


async def test_it_never_asks_and_answers_with_the_summary() -> None:
    tool = TodoWrite()
    plan = TodoList.model_validate(
        {
            "todos": [
                {"content": "Añadir la función", "status": "completed"},
                {"content": "Actualizar los tests", "status": "in_progress"},
            ]
        }
    )

    assert await tool.approval(plan) is None
    result = await tool.run(plan)

    # Unfinished: the model is reminded to keep it current.
    assert result == f"2 tasks: 1 completed, 1 in progress\n{KEEP_CURRENT}"
    assert tool.summary(result) == "2 tasks: 1 completed, 1 in progress"


async def test_a_finished_list_gets_only_its_summary() -> None:
    done = TodoList.model_validate(
        {
            "todos": [
                {"content": "Añadir la función", "status": "completed"},
                {"content": "Renombrar el módulo", "status": "cancelled"},
            ]
        }
    )

    assert await TodoWrite().run(done) == "2 tasks: 1 completed, 1 cancelled"
