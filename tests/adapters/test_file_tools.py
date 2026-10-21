"""The read-only file tools (spec hito 4, §1.6 and §4.6), in `tmp_path`."""

from pathlib import Path

import pytest

from mharness.adapters.tools import ReadFile, Workspace
from mharness.adapters.tools.files import READ_MAX_LINE, ReadFileParams
from mharness.domain.tools import ToolError
from mharness.ports.tools import Tool


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


async def read(root: Path, path: str, **params: int) -> str:
    tool = ReadFile(Workspace(root))
    return await tool.run(ReadFileParams(path=path, **params))


def test_read_file_satisfies_the_port(root: Path) -> None:
    # mypy checks this assignment against the Protocol.
    tool: Tool[ReadFileParams] = ReadFile(Workspace(root))

    assert (tool.name, tool.permission) == ("read_file", "read")


# read_file


async def test_lines_come_numbered(root: Path) -> None:
    write(root, "notas.txt", "Comprar pan\n\nLlamar a Ane\n")

    assert await read(root, "notas.txt") == (
        "     1\tComprar pan\n     2\t\n     3\tLlamar a Ane"
    )


async def test_offset_and_limit(root: Path) -> None:
    write(root, "n.txt", "".join(f"línea {i}\n" for i in range(1, 11)))

    result = await read(root, "n.txt", offset=4, limit=2)

    assert result.splitlines() == [
        "     4\tlínea 4",
        "     5\tlínea 5",
        "… [truncated at line 5; use offset=6 to read more]",
    ]


async def test_long_files_are_cut_with_a_notice(root: Path) -> None:
    write(root, "big.txt", "x\n" * 2500)
    tool = ReadFile(Workspace(root))

    result = await tool.run(ReadFileParams(path="big.txt"))

    assert result.splitlines()[-1] == (
        "… [truncated at line 2000; use offset=2001 to read more]"
    )
    assert tool.summary(result) == "2000 lines (truncated)"


async def test_a_huge_line_is_cut(root: Path) -> None:
    write(root, "one.txt", "a" * (READ_MAX_LINE * 3) + "\nfin\n")

    lines = (await read(root, "one.txt")).splitlines()

    assert lines[0].endswith(" … [line cut]")
    assert lines[1] == "     2\tfin"


async def test_crlf_line_endings(root: Path) -> None:
    (root / "w.txt").write_bytes(b"uno\r\ndos\r\n")

    assert await read(root, "w.txt") == "     1\tuno\n     2\tdos"


async def test_empty_file_and_offset_past_the_end(root: Path) -> None:
    write(root, "empty.txt", "")
    write(root, "short.txt", "uno\n")

    assert await read(root, "empty.txt") == "(empty file)"
    assert await read(root, "short.txt", offset=5) == (
        "(no lines from offset 5: the file has 1 lines)"
    )


@pytest.mark.parametrize(
    ("setup", "path", "message"),
    [
        (lambda root: None, "missing.txt", "file not found: missing.txt"),
        (lambda root: (root / "src").mkdir(), "src", "is a directory"),
        (
            lambda root: (root / "a.bin").write_bytes(b"\x89PNG\0\0"),
            "a.bin",
            "binary file",
        ),
    ],
)
async def test_read_errors(root: Path, setup: object, path: str, message: str) -> None:
    setup(root)  # type: ignore[operator]

    with pytest.raises(ToolError, match=message):
        await read(root, path)


# Perimeter (spec hito 4, §1.6)


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/hostname", "src/../../x"])
async def test_paths_outside_are_refused(root: Path, path: str) -> None:
    write(root.parent, "outside.txt", "fuera")

    with pytest.raises(ToolError, match="outside the working directory"):
        await read(root, path)


async def test_a_link_to_outside_is_refused(root: Path) -> None:
    outside = write(root.parent, "outside.txt", "fuera")
    (root / "link.txt").symlink_to(outside)

    with pytest.raises(ToolError, match="outside the working directory"):
        await read(root, "link.txt")


async def test_a_link_inside_is_read(root: Path) -> None:
    write(root, "real.txt", "dentro\n")
    (root / "link.txt").symlink_to(root / "real.txt")

    assert await read(root, "link.txt") == "     1\tdentro"


# Secret files


@pytest.mark.parametrize("path", [".env", "config/.env.local", ".ssh/id_rsa"])
async def test_secret_files_are_refused(root: Path, path: str) -> None:
    write(root, path, "OPENCODE_API_KEY=sk-inventada")

    with pytest.raises(ToolError, match="secret file"):
        await read(root, path)


async def test_a_link_to_a_secret_is_refused(root: Path) -> None:
    write(root, ".env", "OPENCODE_API_KEY=sk-inventada")
    (root / "notes.txt").symlink_to(root / ".env")

    with pytest.raises(ToolError, match="secret file"):
        await read(root, "notes.txt")


async def test_env_example_is_readable(root: Path) -> None:
    write(root, ".env.example", "OPENCODE_API_KEY=\n")

    assert await read(root, ".env.example") == "     1\tOPENCODE_API_KEY="
