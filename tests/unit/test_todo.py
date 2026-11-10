"""The task list's rules and its summary (spec hito 10, §1.10, and §4,
test 9)."""

import pytest
from pydantic import ValidationError

from mharness.domain.todo import TODO_MAX_CONTENT, TODO_MAX_TASKS, Todo, TodoList


def todos(*statuses: str) -> list[dict[str, str]]:
    return [
        {"content": f"Tarea {number}", "status": status}
        for number, status in enumerate(statuses, 1)
    ]


def test_the_summary_counts_each_status_in_order() -> None:
    plan = TodoList.model_validate(
        {"todos": todos("pending", "in_progress", "completed")}
    )

    assert plan.summary() == "3 tasks: 1 completed, 1 in progress, 1 pending"


def test_the_summary_of_one_task_and_of_cancelled_ones() -> None:
    one = TodoList.model_validate({"todos": todos("completed")})
    two = TodoList.model_validate({"todos": todos("cancelled", "completed")})

    assert one.summary() == "1 task: 1 completed"
    assert two.summary() == "2 tasks: 1 completed, 1 cancelled"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"todos": []}, "at least 1 item"),
        ({"todos": todos(*["pending"] * (TODO_MAX_TASKS + 1))}, "at most 50 items"),
        ({"todos": todos("in_progress", "in_progress")}, "at most one at a time"),
        (
            {"todos": [{"content": "x" * (TODO_MAX_CONTENT + 1), "status": "pending"}]},
            "at most 200 characters",
        ),
        ({"todos": [{"content": "   ", "status": "pending"}]}, "needs some text"),
        ({"todos": [{"content": "Tarea", "status": "done"}]}, "'pending'"),
        ({"todos": [{"content": "Tarea", "status": "pending", "id": 1}]}, "Extra"),
    ],
)
def test_what_breaks_the_rules_is_a_validation_error(
    arguments: dict[str, object], message: str
) -> None:
    # The loop sends it back to the model, which corrects the call.
    with pytest.raises(ValidationError, match=message):
        TodoList.model_validate(arguments)


def test_a_task_is_frozen() -> None:
    task = Todo(content="Tarea", status="pending")

    with pytest.raises(ValidationError):
        task.status = "completed"  # type: ignore[misc]
