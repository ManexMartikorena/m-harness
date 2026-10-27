"""Notas: una pequeña aplicación de línea de comandos.

    python3 notas.py nueva "comprar pan"
    python3 notas.py lista
"""

import argparse
import pathlib
import sys

FICHERO = pathlib.Path("notas.txt")


def leer() -> list[str]:
    """Las notas guardadas, en el orden en que se escribieron."""
    if not FICHERO.exists():
        return []
    return [linea for linea in FICHERO.read_text(encoding="utf-8").splitlines() if linea]


def guardar(notas: list[str]) -> None:
    FICHERO.write_text("".join(nota + "\n" for nota in notas), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="notas")
    ordenes = parser.add_subparsers(dest="orden", required=True)
    nueva = ordenes.add_parser("nueva", help="añade una nota")
    nueva.add_argument("texto")
    ordenes.add_parser("lista", help="muestra las notas, numeradas")
    args = parser.parse_args(argv)
    if args.orden == "nueva":
        guardar([*leer(), args.texto])
        return 0
    for numero, nota in enumerate(leer(), 1):
        print(f"{numero}. {nota}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
