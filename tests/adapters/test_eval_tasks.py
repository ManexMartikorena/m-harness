"""The battery of `evals/` itself (spec hito 8, §1.6 and §4.14): every task
loads, its check fails on the untouched repository (otherwise it measures
nothing) and passes with a reference solution (otherwise it cannot be
passed). Real commands, all harmless; no model."""

import os
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from mharness.adapters.commands import LocalCommandRunner
from mharness.adapters.evals import TomlEvalSuite
from mharness.application.evals import Evaluator
from mharness.domain.environment import command_env

EVALS = Path(__file__).parents[2] / "evals"


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def rename_total(repo: Path) -> None:
    for file in repo.rglob("*.py"):
        text = file.read_text(encoding="utf-8")
        file.write_text(re.sub(r"(?<!\w)total(?=\s*\()", "importe_total", text))


SLUGIFY = """
import re
import unicodedata


def slugify(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plano.lower()).strip("-")
"""

# What a model that gets it right would leave, and answer.
SOLUTIONS: dict[str, tuple[Callable[[Path], object], str]] = {
    "01-version": (lambda repo: None, "La versión es 1.4.2."),
    "02-buscar-funcion": (lambda repo: None, "En src/tienda/iva.py."),
    "03-contar-ficheros": (lambda repo: None, "Hay 6 ficheros .py."),
    "04-gitignore": (
        lambda repo: (repo / ".gitignore").write_text("__pycache__/\n.venv/\n"),
        "Hecho.",
    ),
    "05-puerto": (
        lambda repo: edit(repo / "src/tienda/config.py", "8000", "8080"),
        "Hecho.",
    ),
    "06-arreglar-descuento": (
        lambda repo: edit(
            repo / "src/tienda/descuentos.py",
            "precio * porcentaje / 100",
            "precio * (100 - porcentaje) / 100",
        ),
        "Hecho.",
    ),
    "07-renombrar": (rename_total, "Hecho."),
    "08-slugify": (
        lambda repo: (repo / "texto.py").write_text(SLUGIFY),
        "Hecho.",
    ),
    "09-typo": (
        lambda repo: edit(repo / "README.md", "recieve", "receive"),
        "Fixed.",
    ),
    "10-is-even": (
        lambda repo: edit(
            repo / "utils.py",
            '"""Whether n is odd."""\n    return n % 2 == 1\n',
            '"""Whether n is odd."""\n    return n % 2 == 1\n\n\n'
            "def is_even(n: int) -> bool:\n    return n % 2 == 0\n",
        ),
        "Added.",
    ),
}


def evaluator(suite: TomlEvalSuite) -> Evaluator:
    env = command_env(os.environ)

    def no_runs(*args: object) -> None:
        raise AssertionError("no model here")

    return Evaluator(suite, no_runs, LocalCommandRunner(), env)  # type: ignore[arg-type]


async def test_the_battery_has_ten_tasks_two_for_validation() -> None:
    tasks = await TomlEvalSuite(EVALS).tasks()

    assert [task.id for task in tasks] == list(SOLUTIONS)
    assert [task.id for task in tasks if task.split == "validation"] == [
        "04-gitignore",
        "07-renombrar",
    ]
    # No run_command until hito 15 (decision 2).
    assert all("run_command" not in task.allow for task in tasks)


@pytest.mark.parametrize("task_id", list(SOLUTIONS))
async def test_each_check_fails_untouched_and_passes_when_solved(task_id: str) -> None:
    suite = TomlEvalSuite(EVALS)
    [task] = [task for task in await suite.tasks() if task.id == task_id]
    solve, answer = SOLUTIONS[task_id]
    subject = evaluator(suite)

    async with suite.workspace(task) as repo:
        assert await subject.check(task.check, repo, "") is not None
    async with suite.workspace(task) as repo:
        solve(repo)
        assert await subject.check(task.check, repo, answer) is None
