"""The task list in the terminal (spec hito 10, §1.10, and §4, test 9)."""

from mharness.adapters.cli.todo import BOLD, DIM, RESET, STRIKE, todo_lines
from mharness.domain.todo import TodoList


def plan(*todos: tuple[str, str]) -> TodoList:
    return TodoList.model_validate(
        {"todos": [{"content": c, "status": s} for c, s in todos]}
    )


def test_each_status_has_its_mark() -> None:
    lines = todo_lines(
        plan(
            ("A", "completed"),
            ("B", "in_progress"),
            ("C", "pending"),
            ("D", "cancelled"),
        )
    )

    assert lines == ["  ☑ A", "  ▸ B", "  ☐ C", "  ⊘ D"]


def test_with_color_the_current_task_stands_out() -> None:
    lines = todo_lines(
        plan(
            ("A", "completed"),
            ("B", "in_progress"),
            ("C", "pending"),
            ("D", "cancelled"),
        ),
        color=True,
    )

    assert lines == [
        f"  ☑ {DIM}A{RESET}",
        f"  ▸ {BOLD}B{RESET}",
        "  ☐ C",
        f"  ⊘ {DIM}{STRIKE}D{RESET}",
    ]


def test_a_task_cannot_move_the_cursor_nor_break_the_line() -> None:
    # The tasks come from the model: they must not fake what is on screen.
    [line] = todo_lines(plan(("Uno\x1b[2Adós\ntres", "pending")))

    assert "\x1b" not in line
    assert "\n" not in line
    assert line.startswith("  ☐ Uno")
