"""The core (domain, ports, application) uses only the stdlib and Pydantic.

import-linter checks imports between project modules; this test covers
third-party libraries, which import-linter can only blacklist.
"""

import ast
import sys
from pathlib import Path

import mharness

CORE_PACKAGES = ("domain", "ports", "application")
ALLOWED_THIRD_PARTY = frozenset({"pydantic", "mharness"})
PACKAGE_DIR = Path(mharness.__file__).parent


def forbidden_imports(source: str) -> list[str]:
    """Return the top-level modules imported by `source` that are not allowed."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top not in sys.stdlib_module_names and top not in ALLOWED_THIRD_PARTY:
                found.append(top)
    return found


def module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_DIR.parent).with_suffix("")
    parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
    return ".".join(parts)


def test_core_imports_only_stdlib_and_pydantic() -> None:
    core_files = [
        path
        for package in CORE_PACKAGES
        for path in sorted((PACKAGE_DIR / package).rglob("*.py"))
    ]
    assert core_files, "no core modules found"

    violations = [
        f"{module_name(path)} imports {name}"
        for path in core_files
        for name in forbidden_imports(path.read_text(encoding="utf-8"))
    ]

    assert violations == []


def test_forbidden_imports_detects_third_party() -> None:
    source = (
        "import os\n"
        "import httpx\n"
        "from pydantic import BaseModel\n"
        "from rich.console import Console\n"
        "from mharness.domain import x\n"
        "from . import sibling\n"
    )

    assert forbidden_imports(source) == ["httpx", "rich"]
