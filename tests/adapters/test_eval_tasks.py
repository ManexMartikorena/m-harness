"""The battery of `evals/` itself (spec hito 8, §1.6 and §4.14): every task
loads, its check fails on the untouched repository (otherwise it measures
nothing) and passes with a reference solution (otherwise it cannot be
passed). Real commands, all harmless; no model."""

import os
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from mharness import bootstrap
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


COUNT = """

def contar(citas: list[str]) -> int:
    \"\"\"Cuántas citas hay.\"\"\"
    return len(citas)
"""
ABSOLUTE_ZERO = """def a_fahrenheit(celsius: float) -> float:
    \"\"\"Grados Celsius en grados Fahrenheit.\"\"\"
    if celsius < -273.15:
        raise ValueError("a_fahrenheit: below absolute zero")
    return celsius * 9 / 5 + 32
"""


def count_appointments(repo: Path) -> None:
    append(repo / "citas.py", COUNT)
    edit(
        repo / "CHANGELOG.md",
        "## Sin publicar\n",
        "## Sin publicar\n\n- Añadir contar().\n",
    )


def reject_below_zero(repo: Path) -> None:
    path = repo / "conversor.py"
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: text.index("def a_fahrenheit")] + ABSOLUTE_ZERO)


def rename_fine(repo: Path) -> None:
    """Only the rename, in code and tests."""
    for name in ("prestamos.py", "test_prestamos.py"):
        file = repo / name
        text = file.read_text(encoding="utf-8")
        file.write_text(re.sub(r"(?<![\w.])multa(?=\s*\()", "calcular_multa", text))
    edit(
        repo / "test_prestamos.py",
        "dias_retraso, multa,",
        "dias_retraso, calcular_multa,",
    )


def capped_fine(repo: Path) -> None:
    """The rename, the cap with its test and the README."""
    rename_fine(repo)
    edit(
        repo / "prestamos.py",
        "def calcular_multa(dias: int) -> float:\n"
        '    """Lo que se paga por `dias` de retraso, en euros."""\n'
        "    return dias * MULTA_POR_DIA\n",
        "def calcular_multa(dias: int, tope: float | None = None) -> float:\n"
        '    """Lo que se paga por `dias` de retraso, en euros, como mucho `tope`."""\n'
        "    importe = dias * MULTA_POR_DIA\n"
        "    return importe if tope is None else min(importe, tope)\n",
    )
    edit(
        repo / "test_prestamos.py",
        "    def test_multa_de_un_prestamo",
        "    def test_con_tope(self) -> None:\n"
        "        self.assertEqual(calcular_multa(10, tope=3), 3)\n\n"
        "    def test_multa_de_un_prestamo",
    )
    edit(
        repo / "README.md",
        "- `multa(dias)`: lo que se paga por esos días, a 0,50 € el día.",
        "- `calcular_multa(dias, tope=None)`: lo que se paga por esos días, a "
        "0,50 € el día, como mucho `tope`.",
    )


AGENTS = """# Tienda

## Comandos

- Tests: `PYTHONPATH=src python3 -m unittest`
- Un solo test: `PYTHONPATH=src python3 -m unittest tests.test_pedidos`

## Convenciones

- Los mensajes de commit van en español.
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
    "21-convenciones-agents": (count_appointments, "Hecho."),
    "22-convenciones-claude": (reject_below_zero, "Hecho."),
    "23-varios-pasos": (capped_fine, "Hecho."),
    "24-init": (lambda repo: (repo / "AGENTS.md").write_text(AGENTS), "Hecho."),
}


def evaluator(suite: TomlEvalSuite) -> Evaluator:
    env = command_env(os.environ)

    def no_runs(*args: object) -> None:
        raise AssertionError("no model here")

    return Evaluator(suite, no_runs, LocalCommandRunner(), env)  # type: ignore[arg-type]


async def test_the_battery_and_its_validation_tasks() -> None:
    tasks = await TomlEvalSuite(EVALS).tasks()

    assert [task.id for task in tasks] == list(SOLUTIONS)
    # 20 %: two of the basic ten and two of the hard ten (spec hito 8, §1.6).
    assert [task.id for task in tasks if task.split == "validation"] == [
        "04-gitignore",
        "07-renombrar",
        "14-descuento-volumen",
        "18-parse-duration",
        "23-varios-pasos",
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
        assert await subject.check(task, repo, "") is not None
    async with suite.workspace(task) as repo:
        solve(repo)
        assert await subject.check(task, repo, answer) is None


async def checked(task_id: str, change: Callable[[Path], object], answer: str) -> bool:
    """Whether the check of `task_id` passes on the copy `change` leaves."""
    suite = TomlEvalSuite(EVALS)
    [task] = [task for task in await suite.tasks() if task.id == task_id]
    async with suite.workspace(task) as repo:
        change(repo)
        return await evaluator(suite).check(task, repo, answer) is None


def readme_without_cap(repo: Path) -> None:
    capped_fine(repo)
    edit(repo / "README.md", "tope", "límite")


def no_test_of_the_cap(repo: Path) -> None:
    capped_fine(repo)
    edit(repo / "test_prestamos.py", "calcular_multa(10, tope=3), 3", "1, 1")


@pytest.mark.parametrize(
    # Each step alone is not the task.
    "change",
    [rename_fine, readme_without_cap, no_test_of_the_cap],
)
async def test_the_steps_of_task_23_count_one_by_one(
    change: Callable[[Path], object],
) -> None:
    assert not await checked("23-varios-pasos", change, "Hecho.")


@pytest.mark.parametrize(
    "agents",
    [
        # Each piece counts: the trap, one test alone, what was stressed.
        AGENTS.replace("PYTHONPATH=src ", ""),
        AGENTS.replace(" tests.test_pedidos", ""),
        AGENTS.replace("- Los mensajes de commit van en español.\n", ""),
        # Short: under 200 lines.
        AGENTS + "- Una línea más.\n" * 200,
    ],
    ids=["no-pythonpath", "no-single-test", "not-stressed", "too-long"],
)
async def test_an_agents_md_that_misses_something_does_not_pass(agents: str) -> None:
    def write(repo: Path) -> None:
        (repo / "AGENTS.md").write_text(agents, encoding="utf-8")

    assert not await checked("24-init", write, "Hecho.")


def test_init_in_a_task_is_what_the_conversation_sends(tmp_path: Path) -> None:
    # The eval measures /init as the person types it (spec hito 10, §5).
    sent = bootstrap._eval_instruction("/init los commits en español", tmp_path)

    assert sent == bootstrap._init(tmp_path).text("los commits en español")
    assert str(tmp_path) in sent
    assert bootstrap._eval_instruction("Arregla el IVA", tmp_path) == "Arregla el IVA"


async def test_a_cheat_on_the_tests_does_not_pass() -> None:
    # Deep audit (I1): `return 80` and the other assert turned into `pass`
    # passed task 06; the check ran the copy's own tests.
    def cheat(repo: Path) -> None:
        edit(
            repo / "src/tienda/descuentos.py",
            "return round(precio * porcentaje / 100, 2)",
            "return 80",
        )
        edit(
            repo / "tests/test_descuentos.py",
            "self.assertEqual(aplicar_descuento(59.9, 0), 59.9)",
            "pass",
        )

    assert not await checked("06-arreglar-descuento", cheat, "Hecho.")


async def test_a_wrong_test_of_the_agent_does_not_fail_right_code() -> None:
    # Deep audit (I1): GLM gave the right 105.0 in task 14, and failed on a
    # test it had written itself that expected 99.0.
    def right_code_wrong_test(repo: Path) -> None:
        volume(repo, on=True)
        edit(
            repo / "tests/test_pedidos.py",
            "    def test_resumen(self) -> None:",
            "    def test_volumen(self) -> None:\n"
            "        self.assertEqual(pedidos.total([(10, 10.0), (1, 10.0)]), 99.0)\n\n"
            "    def test_resumen(self) -> None:",
        )

    assert await checked("14-descuento-volumen", right_code_wrong_test, "Hecho.")


async def test_a_deleted_test_is_put_back() -> None:
    def delete(repo: Path) -> None:
        (repo / "test_calendario.py").unlink()

    assert not await checked("15-bisiesto", delete, "Hecho.")


async def test_every_check_that_runs_unittest_names_its_module() -> None:
    # Deep audit (I1): a check runs only the tests it names, never a
    # discovery that would pick up the files the agent added.
    for task in await TomlEvalSuite(EVALS).tasks():
        command = task.check.command or ""
        for found in re.finditer(r"unittest -q(?P<rest>[^&\n]*)", command):
            assert found["rest"].strip(), task.id
            assert "discover" not in found["rest"], task.id


@pytest.mark.parametrize(
    ("task_id", "answer"),
    [
        # Deep audit (I10): `total` has its test, and was not ruled out.
        ("13-funciones-sin-test", "calcular_iva\ntotal"),
        # `\b6\b` took any answer that mentions a 6.
        ("03-contar-ficheros", "Hay 5 ficheros; 6 si cuento __init__.py dos veces."),
        ("03-contar-ficheros", "1 2 3 4 5 6"),
        ("03-contar-ficheros", "Hay 16 ficheros."),
    ],
)
async def test_a_wrong_answer_does_not_pass(task_id: str, answer: str) -> None:
    assert not await checked(task_id, lambda repo: None, answer)


@pytest.mark.parametrize(
    "answer",
    [
        "6",
        "Hay **6** ficheros `.py` dentro de `src/`.",
        # The real answers of GLM in the evals of 2026-11-04: right, and
        # failed by `^\\D*6\\D*$`, because a numbered list or a name like
        # `__init__.py` holds other numbers.
        "Hay **6** ficheros `.py` dentro de `src/` (contando subcarpetas):\n\n"
        "1. `src/tienda/__init__.py`\n2. `src/tienda/config.py`\n"
        "3. `src/tienda/descuentos.py`\n4. `src/tienda/informe.py`\n"
        "5. `src/tienda/iva.py`\n6. `src/tienda/pedidos.py`",
        "**6** ficheros `.py` dentro de `src/` (todos en la subcarpeta `tienda/`).",
    ],
)
async def test_a_right_count_passes_with_more_numbers_after_it(answer: str) -> None:
    assert await checked("03-contar-ficheros", lambda repo: None, answer)


async def test_the_typo_is_fixed_without_losing_the_readme() -> None:
    # Deep audit (I10): a README replaced by "receive" passed task 09.
    def replace(repo: Path) -> None:
        (repo / "README.md").write_text("receive\n", encoding="utf-8")

    assert not await checked("09-typo", replace, "Fixed.")
