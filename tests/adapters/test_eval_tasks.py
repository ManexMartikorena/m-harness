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

PORT_FROM_ENV = """
import os

HOST = "127.0.0.1"
try:
    PORT = int(os.environ.get("TIENDA_PORT", ""))
except ValueError:
    PORT = 8000
MONEDA = "EUR"
"""

ORDERS = """
from tienda.iva import calcular_iva


def _base(linea):
    cantidad, precio = linea[0], linea[1]
    importe = cantidad * precio
    return importe * 0.95 if VOLUMEN and cantidad >= 10 else importe


def total(lineas):
    return round(sum(_base(linea) for linea in lineas), 2)


def total_con_iva(lineas):
    impuesto = 0.0
    for linea in lineas:
        tipo = 0.10 if len(linea) > 2 and linea[2] == "alimentacion" else 0.21
        impuesto += calcular_iva(_base(linea), tipo)
    return round(total(lineas) + impuesto, 2)
"""

LEAP = "return anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0)"

SORTED_LIST = """
    ordenes.add_parser("lista", help="muestra las notas, numeradas").add_argument(
        "--ordenar", action="store_true"
    )
    args = parser.parse_args(argv)
    if args.orden == "nueva":
        guardar([*leer(), args.texto])
        return 0
    notas = sorted(leer(), key=str.lower) if args.ordenar else leer()
    for numero, nota in enumerate(notas, 1):
        print(f"{numero}. {nota}")
    return 0
"""

JSON_NOTES = """
import argparse
import json
import pathlib
import sys

FICHERO = pathlib.Path("notas.json")
ANTIGUO = pathlib.Path("notas.txt")


def leer() -> list[str]:
    if not FICHERO.exists() and ANTIGUO.exists():
        viejas = [n for n in ANTIGUO.read_text(encoding="utf-8").splitlines() if n]
        guardar(viejas)
    if not FICHERO.exists():
        return []
    return json.loads(FICHERO.read_text(encoding="utf-8"))


def guardar(notas: list[str]) -> None:
    FICHERO.write_text(json.dumps(notas, ensure_ascii=False), encoding="utf-8")
"""

DURATION = r"""

import re


def parse_duration(text: str) -> int:
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", text)
    if not text or match is None:
        raise ValueError(f"not a duration: {text!r}")
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds
"""

REMOVE = '''    def remove(self, name: str, quantity: int) -> None:
        """Take stock out."""
        item = self.items.get(name)
        if item is None or quantity > item.quantity:
            raise ValueError(f"cannot remove {quantity} of {name}")
        item.quantity -= quantity
'''

TOTAL_VALUE = """
    def total_value(self) -> float:
        return sum(i.quantity * i.unit_price for i in self.items.values())
"""

TOTAL_VALUE_TEST = """
    def test_total_value(self) -> None:
        stock = Inventory()
        stock.add("pen", 2, 1.5)
        self.assertEqual(stock.total_value(), 3.0)


if __name__ == "__main__":
"""


def volume(repo: Path, on: bool) -> None:
    code = ORDERS.replace("VOLUMEN", str(on))
    (repo / "src/tienda/pedidos.py").write_text(code, encoding="utf-8")


def replace_between(path: Path, start: str, end: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    first, last = text.index(start), text.index(end)
    path.write_text(text[:first] + new + text[last:], encoding="utf-8")


def notes_sorted(repo: Path) -> None:
    start = '    ordenes.add_parser("lista"'
    replace_between(
        repo / "notas.py", start, "\n\nif __name__", SORTED_LIST.strip("\n")
    )


def notes_json(repo: Path) -> None:
    new = JSON_NOTES.lstrip() + "\n\n"
    replace_between(repo / "notas.py", "import argparse", "def main(", new)


def inventory_fix(repo: Path) -> None:
    new = REMOVE + "\n"
    replace_between(repo / "inventory.py", "    def remove(", "    def quantity(", new)


def total_value(repo: Path) -> None:
    with (repo / "inventory.py").open("a", encoding="utf-8") as file:
        file.write(TOTAL_VALUE)
    old = '\n\nif __name__ == "__main__":\n'
    edit(repo / "test_inventory.py", old, TOTAL_VALUE_TEST)


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(text)


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
    "11-puerto-entorno": (
        lambda repo: (repo / "src/tienda/config.py").write_text(PORT_FROM_ENV),
        "Hecho.",
    ),
    "12-iva-reducido": (lambda repo: volume(repo, on=False), "Hecho."),
    "13-funciones-sin-test": (lambda repo: None, "calcular_iva"),
    "14-descuento-volumen": (lambda repo: volume(repo, on=True), "Hecho."),
    "15-bisiesto": (
        lambda repo: edit(repo / "calendario.py", "return anio % 4 == 0", LEAP),
        "Hecho.",
    ),
    "16-notas-ordenar": (notes_sorted, "Hecho."),
    "17-notas-json": (notes_json, "Hecho."),
    "18-parse-duration": (lambda repo: append(repo / "utils.py", DURATION), "Added."),
    "19-inventory-fix": (inventory_fix, "Fixed."),
    "20-total-value": (total_value, "Added."),
}


def evaluator(suite: TomlEvalSuite) -> Evaluator:
    env = command_env(os.environ)

    def no_runs(*args: object) -> None:
        raise AssertionError("no model here")

    return Evaluator(suite, no_runs, LocalCommandRunner(), env)  # type: ignore[arg-type]


async def test_the_battery_has_twenty_tasks_four_for_validation() -> None:
    tasks = await TomlEvalSuite(EVALS).tasks()

    assert [task.id for task in tasks] == list(SOLUTIONS)
    # 20 %: two of the basic ten and two of the hard ten (spec hito 8, §1.6).
    assert [task.id for task in tasks if task.split == "validation"] == [
        "04-gitignore",
        "07-renombrar",
        "14-descuento-volumen",
        "18-parse-duration",
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
