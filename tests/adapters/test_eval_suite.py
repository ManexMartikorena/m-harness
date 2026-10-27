"""`TomlEvalSuite`: the battery in `evals/` (spec hito 8, §1.5 and §1.9), on
temporary folders."""

from datetime import date
from pathlib import Path

import pytest

from mharness.adapters.evals import TomlEvalSuite
from mharness.domain.evals import Baseline, Check, EvalError, stats
from mharness.ports.evals import EvalSuite
from tests.unit.test_evals import run

TASK_TOML = """
instruction = "¿Qué versión declara pyproject.toml?"
fixture = "tienda"
split = "validation"
allow = ["edit_file"]

[limits]
timeout = 60

[check]
answer_contains = ["1.4.2"]
"""


def battery(root: Path, tasks: dict[str, str] | None = None) -> Path:
    """An `evals/` with one fixture and the tasks given."""
    (root / "fixtures" / "tienda" / "src").mkdir(parents=True)
    (root / "fixtures" / "tienda" / "pyproject.toml").write_text('version = "1.4.2"\n')
    (root / "fixtures" / "tienda" / "src" / "a.py").write_text("x = 1\n")
    for name, text in (
        tasks if tasks is not None else {"01-version": TASK_TOML}
    ).items():
        (root / "tasks" / name).mkdir(parents=True)
        (root / "tasks" / name / "task.toml").write_text(text, encoding="utf-8")
    return root


def baseline(day: int, model: str = "glm-5.3-flash") -> Baseline:
    tasks = {"01-version": stats([run("01-version")])}
    return Baseline(
        date=date(2026, 10, day),
        maha="0.7.1",
        commit="a3eb2c7",
        provider="opencode-go",
        model=model,
        repeat=5,
        tasks=tasks,
        total=tasks["01-version"],
    )


def test_satisfies_the_port(tmp_path: Path) -> None:
    # mypy checks this assignment against the Protocol.
    suite: EvalSuite = TomlEvalSuite(tmp_path)

    assert suite is not None


async def test_reads_each_task_with_its_folder_as_id(tmp_path: Path) -> None:
    suite = TomlEvalSuite(battery(tmp_path))

    [task] = await suite.tasks()

    assert task.id == "01-version"
    assert (task.split, task.allow, task.limits.timeout) == (
        "validation",
        ["edit_file"],
        60,
    )
    # A table that sets only one limit keeps the others of a task.
    assert task.limits.max_steps == 25
    assert task.check == Check(answer_contains=["1.4.2"])


async def test_tasks_come_in_the_order_of_their_folders(tmp_path: Path) -> None:
    other = TASK_TOML.replace("validation", "train")
    suite = TomlEvalSuite(battery(tmp_path, {"02-b": other, "01-a": other}))

    assert [task.id for task in await suite.tasks()] == ["01-a", "02-b"]


@pytest.mark.parametrize(
    ("text", "says"),
    [
        ("instruction = ", "invalid TOML"),
        ('instruction = "x"\nfixture = "tienda"\n', "check"),
        (TASK_TOML + 'mood = "happy"\n', "mood: unknown field"),
        (TASK_TOML.replace('"tienda"', '"nope"'), "no fixture 'nope'"),
        ('id = "otro"\n' + TASK_TOML, "id: unknown field"),
        (
            TASK_TOML.replace("timeout = 60", "timeout = 60\nmax_turns = 3"),
            "limits.max_turns: unknown field",
        ),
    ],
)
async def test_a_wrong_task_is_an_error_that_names_it(
    tmp_path: Path, text: str, says: str
) -> None:
    suite = TomlEvalSuite(battery(tmp_path, {"01-mal": text}))

    with pytest.raises(EvalError) as raised:
        await suite.tasks()

    assert "01-mal" in str(raised.value)
    assert says in str(raised.value)


async def test_without_tasks_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(EvalError, match="no tasks in"):
        await TomlEvalSuite(tmp_path).tasks()


async def test_each_run_works_on_its_own_copy(tmp_path: Path) -> None:
    root = battery(tmp_path)
    suite = TomlEvalSuite(root)
    [task] = await suite.tasks()

    async with suite.workspace(task) as one, suite.workspace(task) as other:
        (one / "src" / "a.py").write_text("x = 2\n")
        assert await suite.read(other, "src/a.py") == "x = 1\n"
        assert await suite.read(one, "src/a.py") == "x = 2\n"
        assert await suite.read(one, "nope.txt") is None

    assert not one.exists()
    # The fixture itself is never touched.
    assert (root / "fixtures" / "tienda" / "src" / "a.py").read_text() == "x = 1\n"


async def test_with_keep_the_copies_stay(tmp_path: Path) -> None:
    suite = TomlEvalSuite(battery(tmp_path), keep=True)
    [task] = await suite.tasks()

    async with suite.workspace(task) as copy:
        pass

    assert (copy / "pyproject.toml").exists()


async def test_baselines_are_saved_and_the_latest_of_the_model_found(
    tmp_path: Path,
) -> None:
    suite = TomlEvalSuite(tmp_path)

    first = await suite.save(baseline(20))
    await suite.save(baseline(27))
    again = await suite.save(baseline(27))
    await suite.save(baseline(28, "kimi-k2.7-code"))

    assert first.endswith("baselines/2026-10-20-opencode-go-glm-5.3-flash.json")
    # Two on the same day do not overwrite each other.
    assert again.endswith("baselines/2026-10-27-opencode-go-glm-5.3-flash-2.json")
    latest = await suite.baseline("opencode-go", "glm-5.3-flash")
    assert latest == baseline(27)
    assert await suite.baseline("opencode-go", "otro") is None


async def test_a_broken_baseline_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "baselines").mkdir()
    (tmp_path / "baselines" / "2026-10-27-x.json").write_text("{")

    with pytest.raises(EvalError, match=r"2026-10-27-x\.json"):
        await TomlEvalSuite(tmp_path).baseline("opencode-go", "glm-5.3-flash")
