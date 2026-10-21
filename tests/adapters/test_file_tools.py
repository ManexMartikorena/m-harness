"""The read-only file tools (spec hito 4, §1.6 and §4.6), in `tmp_path`."""

from pathlib import Path

import pytest

from mharness.adapters.tools import Glob, Grep, ListDir, ReadFile, Workspace, files
from mharness.adapters.tools.files import (
    READ_MAX_LINE,
    GlobParams,
    GrepParams,
    ListDirParams,
    ReadFileParams,
)
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
        "(no lines from offset 5: the file has 1 line)"
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


# list_dir


async def list_dir(root: Path, path: str = ".") -> str:
    return await ListDir(Workspace(root)).run(ListDirParams(path=path))


async def test_list_dir_sorted_with_slashes(root: Path) -> None:
    write(root, "b.txt", "")
    write(root, "src/app.py", "")
    write(root, "a.txt", "")

    assert await list_dir(root) == "a.txt\nb.txt\nsrc/"
    assert await list_dir(root, "src") == "app.py"


async def test_list_dir_marks_secrets(root: Path) -> None:
    write(root, ".env", "OPENCODE_API_KEY=sk-inventada")
    write(root, ".ssh/config", "")
    write(root, "notas.txt", "")

    assert await list_dir(root) == ".env [secret]\n.ssh/ [secret]\nnotas.txt"


async def test_list_dir_refuses_a_secret_directory(root: Path) -> None:
    write(root, ".ssh/config", "")

    with pytest.raises(ToolError, match="secret directory"):
        await list_dir(root, ".ssh")


async def test_list_dir_cuts_long_listings(root: Path) -> None:
    for i in range(510):
        write(root, f"f{i:03}.txt", "")
    tool = ListDir(Workspace(root))

    result = await tool.run(ListDirParams())

    assert result.splitlines()[-1] == "… [truncated: 500 of 510 entries shown]"
    assert tool.summary(result) == "500 entries"


async def test_list_dir_errors(root: Path) -> None:
    write(root, "notas.txt", "")

    with pytest.raises(ToolError, match="directory not found"):
        await list_dir(root, "missing")
    with pytest.raises(ToolError, match="not a directory"):
        await list_dir(root, "notas.txt")
    with pytest.raises(ToolError, match="outside the working directory"):
        await list_dir(root, "..")
    # An absolute path inside the working directory is fine.
    assert await list_dir(root, str(root)) == "notas.txt"


async def test_empty_directory(root: Path) -> None:
    tool = ListDir(Workspace(root))

    result = await tool.run(ListDirParams())

    assert (result, tool.summary(result)) == ("(empty directory)", "0 entries")


# glob


async def glob(root: Path, pattern: str, path: str = ".") -> str:
    return await Glob(Workspace(root)).run(GlobParams(pattern=pattern, path=path))


async def test_glob_finds_files_recursively(root: Path) -> None:
    write(root, "main.py", "")
    write(root, "src/app.py", "")
    write(root, "src/sub/util.py", "")
    write(root, "src/notes.md", "")

    assert await glob(root, "**/*.py") == "main.py\nsrc/app.py\nsrc/sub/util.py"
    assert await glob(root, "*.py") == "main.py"
    # Relative to `path`, results relative to the working directory.
    assert await glob(root, "*.py", "src") == "src/app.py"


async def test_glob_skips_heavy_and_secret_places(root: Path) -> None:
    write(root, "app.py", "")
    write(root, ".git/hooks/x.py", "")
    write(root, ".venv/lib/y.py", "")
    write(root, "node_modules/z.py", "")
    write(root, ".ssh/k.py", "")
    write(root, ".env", "")

    assert await glob(root, "**/*.py") == "app.py"
    assert await glob(root, "**/.env*") == "(no files match)"


async def test_glob_skips_links_to_outside(root: Path) -> None:
    outside = write(root.parent, "outside.py", "")
    (root / "link.py").symlink_to(outside)
    write(root, "in.py", "")

    assert await glob(root, "*.py") == "in.py"


async def test_glob_cuts_long_results(root: Path) -> None:
    for i in range(205):
        write(root, f"f{i:03}.txt", "")
    tool = Glob(Workspace(root))

    result = await tool.run(GlobParams(pattern="*.txt"))

    assert result.splitlines()[-1] == "… [truncated: 200 of 205 files shown]"
    assert tool.summary(result) == "200 files"


async def test_glob_stops_on_huge_trees(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files, "WALK_MAX_FILES", 3)
    for i in range(5):
        write(root, f"f{i}.txt", "")

    result = await glob(root, "*.txt")

    assert result.splitlines()[-1] == "… [stopped after 3 files; narrow the path]"


@pytest.mark.parametrize("pattern", ["/etc/*", "../*.py", "src/../../*"])
async def test_glob_refuses_patterns_that_escape(root: Path, pattern: str) -> None:
    with pytest.raises(ToolError, match="must be relative"):
        await glob(root, pattern)


# grep


async def grep(root: Path, pattern: str, **params: str) -> str:
    return await Grep(Workspace(root)).run(GrepParams(pattern=pattern, **params))


async def test_grep_gives_path_line_and_text(root: Path) -> None:
    write(root, "src/sse.py", "import re\n\nasync def parse_sse(chunks):\n")
    write(root, "main.py", "def main():\n    parse_sse(x)\n")

    assert await grep(root, r"parse_sse") == (
        "main.py:2:     parse_sse(x)\nsrc/sse.py:3: async def parse_sse(chunks):"
    )


async def test_grep_filters_by_glob(root: Path) -> None:
    write(root, "a.py", "Ane\n")
    write(root, "src/b.py", "Ane\n")
    write(root, "c.md", "Ane\n")

    assert await grep(root, "Ane", glob="*.py") == "a.py:1: Ane\nsrc/b.py:1: Ane"
    assert await grep(root, "Ane", glob="src/*.py") == "src/b.py:1: Ane"


async def test_grep_in_one_file(root: Path) -> None:
    write(root, "a.txt", "uno\ndos\n")
    write(root, ".env", "dos=sk-inventada\n")

    assert await grep(root, "dos", path="a.txt") == "a.txt:2: dos"
    with pytest.raises(ToolError, match="secret file"):
        await grep(root, "dos", path=".env")


async def test_grep_skips_secrets_binaries_and_heavy_dirs(root: Path) -> None:
    write(root, ".env", "OPENCODE_API_KEY=sk-inventada\n")
    write(root, ".ssh/config", "KEY\n")
    write(root, ".git/config", "KEY\n")
    (root / "img.bin").write_bytes(b"KEY\0\0")
    write(root, "notes.txt", "no key here\n")

    assert await grep(root, "KEY") == "(no matches)"


async def test_grep_skips_large_files(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files, "GREP_MAX_FILE_BYTES", 10)
    write(root, "big.txt", "Ane\n" * 10)
    write(root, "small.txt", "Ane\n")

    assert await grep(root, "Ane") == "small.txt:1: Ane"


async def test_grep_cuts_lines_and_results(root: Path) -> None:
    write(root, "long.txt", "x" * 1000 + "\n")
    write(root, "many.txt", "Ane\n" * 150)
    tool = Grep(Workspace(root))

    long_line = await tool.run(GrepParams(pattern="x", path="long.txt"))
    many = await tool.run(GrepParams(pattern="Ane", path="many.txt"))

    assert len(long_line) == len("long.txt:1: ") + 300
    assert many.splitlines()[-1] == "… [stopped at 100 matches; narrow the search]"
    assert tool.summary(many) == "100 matches"


async def test_grep_errors(root: Path) -> None:
    with pytest.raises(ToolError, match="invalid regular expression"):
        await grep(root, "(unclosed")
    with pytest.raises(ToolError, match="not found"):
        await grep(root, "x", path="missing")
    with pytest.raises(ToolError, match="must be relative"):
        await grep(root, "x", glob="../*.py")


async def test_grep_exactly_at_the_limit_has_no_notice(root: Path) -> None:
    write(root, "many.txt", "Ane\n" * 100)

    result = await grep(root, "Ane")

    assert len(result.splitlines()) == 100
    assert "stopped" not in result


async def test_summaries_use_the_singular_for_one(root: Path) -> None:
    write(root, "a.txt", "Ane\n")
    workspace = Workspace(root)

    read_one = await ReadFile(workspace).run(ReadFileParams(path="a.txt"))
    listed = await ListDir(workspace).run(ListDirParams())
    globbed = await Glob(workspace).run(GlobParams(pattern="*.txt"))
    grepped = await Grep(workspace).run(GrepParams(pattern="Ane"))

    assert ReadFile(workspace).summary(read_one) == "1 line"
    assert ListDir(workspace).summary(listed) == "1 entry"
    assert Glob(workspace).summary(globbed) == "1 file"
    assert Grep(workspace).summary(grepped) == "1 match"
    assert Grep(workspace).summary("(no matches)") == "0 matches"
