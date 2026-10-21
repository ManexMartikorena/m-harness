"""The file tools (spec hito 4, §1.6 and §4.6, and spec hito 5, §1.6, §1.7,
§4.3 and §4.4), in `tmp_path`."""

import asyncio
import os
import stat
from pathlib import Path

import pytest

from mharness.adapters.tools import (
    Glob,
    Grep,
    ListDir,
    ReadFile,
    Workspace,
    WriteFile,
    files,
)
from mharness.adapters.tools.files import (
    READ_MAX_LINE,
    GlobParams,
    GrepParams,
    ListDirParams,
    ReadFileParams,
    WriteFileParams,
)
from mharness.domain.approval import ApprovalRequest
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


def test_reading_asks_for_no_approval(root: Path) -> None:
    # Inside and not secret: READ runs without asking (spec hito 5, §1.6).
    workspace = Workspace(root)

    assert ReadFile(workspace).approval(ReadFileParams(path="a.txt")) is None
    assert ListDir(workspace).approval(ListDirParams()) is None
    assert Glob(workspace).approval(GlobParams(pattern="**/*.py")) is None
    assert Grep(workspace).approval(GrepParams(pattern="def")) is None


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


# Perimeter (spec hito 4, §1.6; with approval, spec hito 5, §1.6)

OUTSIDE = "outside the working directory"
SECRET_FILE = "secret file: its content goes to the model provider"
SECRET_DIR = "secret directory: its file names go to the model provider"


@pytest.mark.parametrize(
    "path", ["../outside.txt", "{parent}/outside.txt", "src/../../outside.txt"]
)
async def test_paths_outside_ask_and_are_read_once_approved(
    root: Path, path: str
) -> None:
    outside = write(root.parent, "outside.txt", "fuera")
    tool = ReadFile(Workspace(root))
    params = ReadFileParams(path=path.format(parent=root.parent))

    request = tool.approval(params)

    assert request is not None
    assert (request.tool, request.title) == ("read_file", f"read {outside}")
    assert (request.scope, request.warning) == (None, OUTSIDE)
    assert await tool.run(params) == "     1\tfuera"


async def test_a_link_to_outside_asks_with_the_real_path(root: Path) -> None:
    outside = write(root.parent, "outside.txt", "fuera")
    (root / "link.txt").symlink_to(outside)
    tool = ReadFile(Workspace(root))

    request = tool.approval(ReadFileParams(path="link.txt"))

    assert request == ApprovalRequest(
        tool="read_file",
        title=f"read {outside}",
        detail=f"{outside} (asked: link.txt)",
        scope=None,
        warning=OUTSIDE,
    )


async def test_a_link_inside_is_read(root: Path) -> None:
    write(root, "real.txt", "dentro\n")
    (root / "link.txt").symlink_to(root / "real.txt")

    assert await read(root, "link.txt") == "     1\tdentro"


# Secret files


@pytest.mark.parametrize("path", [".env", "config/.env.local", ".ssh/id_rsa"])
async def test_secret_files_ask_and_are_read_once_approved(
    root: Path, path: str
) -> None:
    write(root, path, "OPENCODE_API_KEY=sk-inventada")
    tool = ReadFile(Workspace(root))
    params = ReadFileParams(path=path)

    request = tool.approval(params)

    assert request == ApprovalRequest(
        tool="read_file",
        title=f"read {path}",
        detail=str(root / path),
        scope=None,
        warning=SECRET_FILE,
    )
    assert await tool.run(params) == "     1\tOPENCODE_API_KEY=sk-inventada"


async def test_a_link_to_a_secret_asks_with_the_real_path(root: Path) -> None:
    write(root, ".env", "OPENCODE_API_KEY=sk-inventada")
    (root / "notes.txt").symlink_to(root / ".env")
    tool = ReadFile(Workspace(root))

    request = tool.approval(ReadFileParams(path="notes.txt"))

    assert request is not None
    assert request.title == "read .env"
    assert request.detail == f"{root / '.env'} (asked: notes.txt)"
    assert request.warning == SECRET_FILE


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


async def test_list_dir_asks_for_a_secret_directory(root: Path) -> None:
    write(root, ".ssh/config", "")
    tool = ListDir(Workspace(root))
    params = ListDirParams(path=".ssh")

    request = tool.approval(params)

    assert request is not None
    assert (request.tool, request.title) == ("list_dir", "list .ssh")
    assert (request.scope, request.warning) == (None, SECRET_DIR)
    assert await tool.run(params) == "config [secret]"


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
    request = ListDir(Workspace(root)).approval(ListDirParams(path=".."))
    assert request is not None
    assert request.warning == OUTSIDE
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
    request = Grep(Workspace(root)).approval(GrepParams(pattern="dos", path=".env"))
    assert request is not None
    assert request.warning == SECRET_FILE


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


# Reading outside or a secret, with approval (spec hito 5, §1.6 and §4.3)


@pytest.fixture
def other(root: Path) -> Path:
    """A directory next to the working directory, so outside it."""
    other = root.parent / "other"
    write(other, "a.py", "Ane\n")
    write(other, "sub/b.py", "Ane\n")
    write(other, ".env", "Ane=sk-inventada\n")
    write(other, ".ssh/k.py", "Ane\n")
    return other


async def test_list_dir_outside_asks_and_marks_secrets(root: Path, other: Path) -> None:
    tool = ListDir(Workspace(root))
    params = ListDirParams(path="../other")

    request = tool.approval(params)

    assert request == ApprovalRequest(
        tool="list_dir",
        title=f"list {other}",
        detail=f"{other} (asked: ../other)",
        scope=None,
        warning=OUTSIDE,
    )
    # The absolute path decides what is secret (decision D4).
    assert await tool.run(params) == ".env [secret]\n.ssh/ [secret]\na.py\nsub/"


async def test_glob_outside_asks_and_stays_in_the_approved_directory(
    root: Path, other: Path
) -> None:
    write(root, "in.py", "")
    write(root.parent, "elsewhere.py", "")
    # Both leave the approved directory: skipped (decision D2).
    (other / "in.py").symlink_to(root / "in.py")
    (other / "up.py").symlink_to(root.parent / "elsewhere.py")
    tool = Glob(Workspace(root))
    params = GlobParams(pattern="**/*.py", path="../other")

    request = tool.approval(params)

    assert request is not None
    assert (request.tool, request.title) == ("glob", f"glob **/*.py in {other}")
    assert (request.scope, request.warning) == (None, OUTSIDE)
    # Absolute paths (decision D3); secrets skipped (decision D4).
    assert await tool.run(params) == f"{other}/a.py\n{other}/sub/b.py"


async def test_grep_outside_asks_and_gives_absolute_paths(
    root: Path, other: Path
) -> None:
    (other / "up.py").symlink_to(write(root.parent, "elsewhere.py", "Ane\n"))
    tool = Grep(Workspace(root))
    folder = GrepParams(pattern="Ane", path="../other", glob="*.py")
    one_file = GrepParams(pattern="Ane", path="../other/a.py")

    request = tool.approval(folder)

    assert request is not None
    assert (request.tool, request.title) == (
        "grep",
        f'grep "Ane" in {other} (glob: *.py)',
    )
    assert (request.scope, request.warning) == (None, OUTSIDE)
    assert await tool.run(folder) == f"{other}/a.py:1: Ane\n{other}/sub/b.py:1: Ane"
    assert tool.approval(one_file) is not None
    assert await tool.run(one_file) == f"{other}/a.py:1: Ane"


async def test_a_search_outside_shows_every_path_absolute(root: Path) -> None:
    # Decision D3, also for the files of the working directory.
    write(root, "in.py", "Ane\n")
    write(root.parent, "up.py", "Ane\n")
    workspace = Workspace(root)
    globbing = GlobParams(pattern="**/*.py", path="..")
    grepping = GrepParams(pattern="Ane", path="..")

    globber, searcher = Glob(workspace), Grep(workspace)

    assert globber.approval(globbing) is not None
    assert searcher.approval(grepping) is not None
    assert await globber.run(globbing) == f"{root.parent}/up.py\n{root}/in.py"
    assert await searcher.run(grepping) == (
        f"{root.parent}/up.py:1: Ane\n{root}/in.py:1: Ane"
    )


async def test_outside_and_secret_give_both_warnings(root: Path, other: Path) -> None:
    # Decisions D5 and D6: outside first, then the secret.
    workspace = Workspace(root)

    read_request = ReadFile(workspace).approval(ReadFileParams(path="../other/.env"))
    list_request = ListDir(workspace).approval(ListDirParams(path="../other/.ssh"))
    grep_request = Grep(workspace).approval(
        GrepParams(pattern="Ane", path="../other/.env")
    )

    assert read_request is not None
    assert read_request.warning == f"{OUTSIDE}; {SECRET_FILE}"
    assert list_request is not None
    assert list_request.warning == f"{OUTSIDE}; {SECRET_DIR}"
    assert grep_request is not None
    assert grep_request.warning == f"{OUTSIDE}; {SECRET_FILE}"


async def test_grep_on_a_secret_file_asks_and_is_read_once_approved(
    root: Path,
) -> None:
    # Decision D7: grep on one secret file asks, as read_file.
    write(root, ".env", "dos=sk-inventada\n")
    tool = Grep(Workspace(root))
    params = GrepParams(pattern="dos", path=".env")

    request = tool.approval(params)

    assert request == ApprovalRequest(
        tool="grep",
        title='grep "dos" in .env',
        detail=str(root / ".env"),
        scope=None,
        warning=SECRET_FILE,
    )
    assert await tool.run(params) == ".env:1: dos=sk-inventada"


async def test_searching_skips_secrets_and_links_out_without_asking(
    root: Path,
) -> None:
    write(root, ".env", "Ane\n")
    write(root, ".ssh/config", "Ane\n")
    write(root, "notes.py", "Ane\n")
    (root / "out.py").symlink_to(write(root.parent, "outside.py", "Ane\n"))
    workspace = Workspace(root)
    globbing = GlobParams(pattern="**/*")
    grepping = GrepParams(pattern="Ane")
    # A secret directory as the path: skipped as today (decision D7).
    in_secret_dir = GrepParams(pattern="Ane", path=".ssh")

    assert Glob(workspace).approval(globbing) is None
    assert Grep(workspace).approval(grepping) is None
    assert Grep(workspace).approval(in_secret_dir) is None
    assert await Glob(workspace).run(globbing) == "notes.py"
    assert await Grep(workspace).run(grepping) == "notes.py:1: Ane"
    assert await Grep(workspace).run(in_secret_dir) == "(no matches)"


async def test_cheap_failures_come_before_the_question(root: Path, other: Path) -> None:
    # Decision D8: what run() would refuse is refused before asking.
    (other / "img.bin").write_bytes(b"\x89PNG\0\0")
    workspace = Workspace(root)

    with pytest.raises(ToolError, match="file not found"):
        ReadFile(workspace).approval(ReadFileParams(path="../missing"))
    with pytest.raises(ToolError, match="is a directory"):
        ReadFile(workspace).approval(ReadFileParams(path="../other"))
    with pytest.raises(ToolError, match="binary file"):
        ReadFile(workspace).approval(ReadFileParams(path="../other/img.bin"))
    with pytest.raises(ToolError, match="directory not found"):
        ListDir(workspace).approval(ListDirParams(path="../missing"))
    with pytest.raises(ToolError, match="not a directory"):
        ListDir(workspace).approval(ListDirParams(path="../other/a.py"))
    with pytest.raises(ToolError, match="must be relative"):
        Glob(workspace).approval(GlobParams(pattern="../*", path="../other"))
    with pytest.raises(ToolError, match="not a directory"):
        Glob(workspace).approval(GlobParams(pattern="*", path="../other/a.py"))
    with pytest.raises(ToolError, match="invalid regular expression"):
        Grep(workspace).approval(GrepParams(pattern="(", path="../other"))
    with pytest.raises(ToolError, match="must be relative"):
        Grep(workspace).approval(GrepParams(pattern="x", path="../o", glob="/x"))
    with pytest.raises(ToolError, match="not found"):
        Grep(workspace).approval(GrepParams(pattern="x", path="../missing"))
    # Inside and not secret, nothing to ask: run() gives the error, as before.
    assert ReadFile(workspace).approval(ReadFileParams(path="missing")) is None


# What was asked is what is read (decision D1: TOCTOU)


async def test_a_link_changed_after_the_question_is_not_read(root: Path) -> None:
    first = write(root.parent, "first.txt", "uno")
    second = write(root.parent, "second.txt", "dos")
    link = root / "link.txt"
    link.symlink_to(first)
    tool = ReadFile(Workspace(root))
    params = ReadFileParams(path="link.txt")

    request = tool.approval(params)
    link.unlink()
    link.symlink_to(second)

    assert request is not None
    assert request.title == f"read {first}"
    with pytest.raises(
        ToolError, match=r"link\.txt changed after the question; ask again"
    ):
        await tool.run(params)


async def test_a_link_that_leaves_after_no_question_is_not_read(
    root: Path,
) -> None:
    write(root, "real.txt", "dentro")
    write(root, ".env", "OPENCODE_API_KEY=sk-inventada")
    link = root / "link.txt"
    link.symlink_to(root / "real.txt")
    tool = ReadFile(Workspace(root))
    params = ReadFileParams(path="link.txt")

    assert tool.approval(params) is None
    link.unlink()
    link.symlink_to(root / ".env")

    with pytest.raises(
        ToolError, match=r"link\.txt changed after the question; ask again"
    ):
        await tool.run(params)


async def test_each_question_replaces_the_last_one(root: Path) -> None:
    write(root.parent, "outside.txt", "fuera")
    write(root, "a.txt", "dentro")
    workspace = Workspace(root)
    outside = ReadFileParams(path="../outside.txt")
    other_outside = ListDirParams(path="..")

    reader = ReadFile(workspace)
    assert reader.approval(outside) is not None
    assert reader.approval(ReadFileParams(path="a.txt")) is None
    with pytest.raises(ToolError, match="changed after the question"):
        await reader.run(outside)
    # Without asking at all, an outside path is not read either.
    with pytest.raises(ToolError, match="changed after the question"):
        await ListDir(workspace).run(other_outside)
    with pytest.raises(ToolError, match="changed after the question"):
        await Glob(workspace).run(GlobParams(pattern="*", path=".."))
    with pytest.raises(ToolError, match="changed after the question"):
        await Grep(workspace).run(GrepParams(pattern="x", path=".."))


# write_file (spec hito 5, §1.7 and §4.4.1)


def write_tool(root: Path) -> WriteFile:
    return WriteFile(Workspace(root))


def ask_write(tool: WriteFile, path: str, content: str) -> ApprovalRequest:
    request = tool.approval(WriteFileParams(path=path, content=content))
    assert request is not None
    return request


def test_write_file_satisfies_the_port(root: Path) -> None:
    # mypy checks this assignment against the Protocol.
    tool: Tool[WriteFileParams] = write_tool(root)

    assert (tool.name, tool.permission) == ("write_file", "effect")
    # The exact description of spec hito 5, §3.2.
    assert tool.description == (
        "Create or overwrite a text file in the working directory. The user "
        'approves it first. Example: {"path": "notes.txt", "content": "…"}'
    )


async def test_creating_asks_with_a_preview_and_writes(root: Path) -> None:
    tool = write_tool(root)
    params = WriteFileParams(path="notas.txt", content="uno\ndos\ntres\n")

    request = tool.approval(params)
    result = await tool.run(params)

    assert request == ApprovalRequest(
        tool="write_file",
        title="create notas.txt (3 lines)",
        detail="uno\ndos\ntres",
        scope="write_file",
    )
    assert result == "wrote notas.txt (3 lines)"
    assert tool.summary(result) == "3 lines"
    assert (root / "notas.txt").read_bytes() == b"uno\ndos\ntres\n"


async def test_the_preview_shows_the_first_20_lines(root: Path) -> None:
    tool = write_tool(root)
    content = "".join(f"línea {i}\n" for i in range(1, 26))

    detail = ask_write(tool, "long.txt", content).detail

    assert detail.splitlines() == [
        *(f"línea {i}" for i in range(1, 21)),
        "… [5 more lines]",
    ]
    assert ask_write(tool, "empty.txt", "") == ApprovalRequest(
        tool="write_file",
        title="create empty.txt (0 lines)",
        detail="(empty file)",
        scope="write_file",
    )


@pytest.mark.parametrize(
    ("content", "lines"),
    [
        ("a\nb\nc", "3 lines"),
        ("a\nb\nc\n", "3 lines"),
        ("", "0 lines"),
        ("a\n\n", "2 lines"),
        ("a\r\nb\rc", "3 lines"),
        ("x", "1 line"),
    ],
)
async def test_lines_are_counted_as_read_file_numbers_them(
    root: Path, content: str, lines: str
) -> None:
    # Decision W3.
    tool = write_tool(root)
    params = WriteFileParams(path="n.txt", content=content)

    assert tool.approval(params) is not None
    assert await tool.run(params) == f"wrote n.txt ({lines})"


async def test_overwriting_asks_with_a_diff(root: Path) -> None:
    write(root, "notas.txt", "a\nb\nc\n")
    tool = write_tool(root)
    params = WriteFileParams(path="notas.txt", content="a\nB\nc\n")

    request = tool.approval(params)
    result = await tool.run(params)

    # Decision W4: no "---"/"+++" header; the path is in the title.
    assert request == ApprovalRequest(
        tool="write_file",
        title="overwrite notas.txt",
        detail="@@ -1,3 +1,3 @@\n a\n-b\n+B\n c",
        scope="write_file",
    )
    assert result == "wrote notas.txt (3 lines)"
    assert (root / "notas.txt").read_text(encoding="utf-8") == "a\nB\nc\n"


async def test_a_long_diff_is_cut_at_60_lines(root: Path) -> None:
    # Decision W1: as edit_file (spec hito 5, §1.8).
    write(root, "big.txt", "".join(f"old {i}\n" for i in range(100)))
    content = "".join(f"new {i}\n" for i in range(100))

    lines = ask_write(write_tool(root), "big.txt", content).detail.splitlines()

    # 1 hunk header + 100 removed + 100 added = 201 lines.
    assert len(lines) == 61
    assert lines[0] == "@@ -1,100 +1,100 @@"
    assert lines[-1] == "… [141 more diff lines]"


async def test_writing_creates_the_folders(root: Path) -> None:
    tool = write_tool(root)
    params = WriteFileParams(path="a/b/c.txt", content="hola\n")

    assert ask_write(tool, "a/b/c.txt", "hola\n").title == "create a/b/c.txt (1 line)"
    await tool.run(params)

    assert (root / "a/b/c.txt").read_text(encoding="utf-8") == "hola\n"


async def test_content_is_written_as_is(root: Path) -> None:
    tool = write_tool(root)
    params = WriteFileParams(path="w.txt", content="año\r\ndos\r\n")

    tool.approval(params)
    await tool.run(params)

    assert (root / "w.txt").read_bytes() == "año\r\ndos\r\n".encode()


@pytest.mark.parametrize(
    ("path", "scope", "warning"),
    [
        ("notas.txt", "write_file", None),
        ("../fuera.txt", None, OUTSIDE),
        (".env", None, SECRET_FILE),
        ("../.env", None, f"{OUTSIDE}; {SECRET_FILE}"),
    ],
)
def test_write_scope_inside_and_none_outside_or_secret(
    root: Path, path: str, scope: str | None, warning: str | None
) -> None:
    request = ask_write(write_tool(root), path, "x\n")

    assert (request.scope, request.warning) == (scope, warning)


def test_writing_over_a_directory_fails_before_asking(root: Path) -> None:
    (root / "src").mkdir()

    with pytest.raises(ToolError, match="is a directory: src"):
        write_tool(root).approval(WriteFileParams(path="src", content="x"))


def test_an_existing_file_must_be_utf8_text(root: Path) -> None:
    # Decision W2.
    (root / "img.bin").write_bytes(b"\x89PNG\0\0")
    (root / "latin1.txt").write_bytes(b"caf\xe9\n")
    tool = write_tool(root)

    with pytest.raises(ToolError, match=r"binary file, not writable: img\.bin"):
        tool.approval(WriteFileParams(path="img.bin", content="x"))
    with pytest.raises(ToolError, match=r"not a UTF-8 text file: latin1\.txt"):
        tool.approval(WriteFileParams(path="latin1.txt", content="x"))


def test_the_same_content_is_nothing_to_change(root: Path) -> None:
    # Decision W5.
    write(root, "notas.txt", "a\nb\n")
    tool = write_tool(root)

    with pytest.raises(ToolError, match="nothing to change"):
        tool.approval(WriteFileParams(path="notas.txt", content="a\nb\n"))
    request = ask_write(tool, "notas.txt", "a\r\nb\r\n")
    assert request.detail == "(only line endings change)"


async def test_a_link_shows_its_target_and_is_kept(root: Path) -> None:
    # Decision W7, and the link survives the atomic write.
    write(root, "real.txt", "uno\n")
    (root / "notes.txt").symlink_to(root / "real.txt")
    tool = write_tool(root)
    params = WriteFileParams(path="notes.txt", content="dos\n")

    request = tool.approval(params)
    await tool.run(params)

    assert request is not None
    assert request.title == "overwrite real.txt"
    assert request.detail == "(asked: notes.txt)\n@@ -1 +1 @@\n-uno\n+dos"
    assert (root / "notes.txt").is_symlink()
    assert (root / "real.txt").read_text(encoding="utf-8") == "dos\n"


def test_cheap_write_failures_come_before_the_question(root: Path) -> None:
    # Decisions W8 and A3.
    write(root, "notas.txt", "")
    os.mkfifo(root / "pipe")
    tool = write_tool(root)

    with pytest.raises(ToolError, match=r"not a directory: notas\.txt"):
        tool.approval(WriteFileParams(path="notas.txt/x.txt", content="x"))
    with pytest.raises(ToolError, match="content is not valid UTF-8"):
        tool.approval(WriteFileParams(path="x.txt", content="\ud800"))
    with pytest.raises(ToolError, match="not a regular file: pipe"):
        tool.approval(WriteFileParams(path="pipe", content="x"))


# write_file: what was shown is what is written (decisions D1 and W6)


async def test_a_file_created_after_the_question_is_not_overwritten(
    root: Path,
) -> None:
    tool = write_tool(root)
    params = WriteFileParams(path="notas.txt", content="mío\n")

    tool.approval(params)
    write(root, "notas.txt", "de otro\n")

    with pytest.raises(ToolError, match=r"notas\.txt changed after the question"):
        await tool.run(params)
    assert (root / "notas.txt").read_text(encoding="utf-8") == "de otro\n"


async def test_a_file_changed_after_the_question_is_not_overwritten(
    root: Path,
) -> None:
    write(root, "notas.txt", "uno\n")
    tool = write_tool(root)
    params = WriteFileParams(path="notas.txt", content="dos\n")

    tool.approval(params)
    write(root, "notas.txt", "tres\n")

    with pytest.raises(ToolError, match=r"notas\.txt changed after the question"):
        await tool.run(params)
    assert (root / "notas.txt").read_text(encoding="utf-8") == "tres\n"


async def test_a_write_link_changed_after_the_question_is_not_followed(
    root: Path,
) -> None:
    write(root, "a.txt", "uno\n")
    write(root, "b.txt", "uno\n")
    link = root / "link.txt"
    link.symlink_to(root / "a.txt")
    tool = write_tool(root)
    params = WriteFileParams(path="link.txt", content="dos\n")

    tool.approval(params)
    link.unlink()
    link.symlink_to(root / "b.txt")

    with pytest.raises(ToolError, match=r"link\.txt changed after the question"):
        await tool.run(params)
    assert (root / "b.txt").read_text(encoding="utf-8") == "uno\n"


async def test_writing_without_a_question_is_refused(root: Path) -> None:
    tool = write_tool(root)
    params = WriteFileParams(path="notas.txt", content="x")

    with pytest.raises(ToolError, match="changed after the question"):
        await tool.run(params)
    tool.approval(params)
    tool.approval(WriteFileParams(path="otra.txt", content="x"))
    with pytest.raises(ToolError, match="changed after the question"):
        await tool.run(params)
    assert not (root / "notas.txt").exists()


# write_file: the atomic write (decision of the maintainer, and A1, A2)


def temporaries(folder: Path) -> list[str]:
    return [p.name for p in folder.iterdir() if p.name.endswith(".tmp")]


@pytest.mark.parametrize(
    ("broken", "failure"),
    [("fsync", OSError), ("replace", OSError), ("fsync", asyncio.CancelledError)],
)
async def test_a_failed_write_keeps_the_original_and_no_temporary(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    broken: str,
    failure: type[BaseException],
) -> None:
    write(root, "notas.txt", "uno\n")
    tool = write_tool(root)
    params = WriteFileParams(path="notas.txt", content="dos\n")
    tool.approval(params)

    def fail(*args: object) -> None:
        if failure is OSError:
            raise OSError(28, "No space left on device")
        raise failure

    monkeypatch.setattr(os, broken, fail)
    expected = ToolError if failure is OSError else failure
    with pytest.raises(expected) as caught:
        await tool.run(params)
    monkeypatch.undo()

    if failure is OSError:
        # Decision A2.
        assert str(caught.value) == ("cannot write notas.txt: No space left on device")
    assert (root / "notas.txt").read_text(encoding="utf-8") == "uno\n"
    assert temporaries(root) == []


async def test_an_overwrite_keeps_the_mode(root: Path) -> None:
    script = write(root, "run.sh", "echo uno\n")
    script.chmod(0o755)
    tool = write_tool(root)
    params = WriteFileParams(path="run.sh", content="echo dos\n")

    tool.approval(params)
    await tool.run(params)

    assert stat.S_IMODE(script.stat().st_mode) == 0o755
    assert temporaries(root) == []


async def test_a_new_file_gets_the_mode_of_the_umask(root: Path) -> None:
    # As open("w") would create it, not the 0600 of mkstemp (decision A1).
    reference = write(root, "reference.txt", "")
    tool = write_tool(root)
    params = WriteFileParams(path="nuevo.txt", content="x\n")

    tool.approval(params)
    await tool.run(params)

    mode = stat.S_IMODE((root / "nuevo.txt").stat().st_mode)
    assert mode == stat.S_IMODE(reference.stat().st_mode)
    assert mode != 0o600


def same_file(a: os.stat_result, b: os.stat_result) -> bool:
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


async def test_the_rename_is_flushed_to_the_disk(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The fsync of the file does not cover its entry in the folder (fsync(2)):
    # the folder gets its own fsync after the rename (decision of the
    # maintainer).
    write(root, "sub/notas.txt", "uno\n")
    tool = write_tool(root)
    params = WriteFileParams(path="sub/notas.txt", content="dos\n")
    tool.approval(params)
    synced: list[os.stat_result] = []
    real_fsync = os.fsync

    def spy(descriptor: int) -> None:
        synced.append(os.fstat(descriptor))
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", spy)
    await tool.run(params)
    monkeypatch.undo()

    file, folder = synced
    assert same_file(file, (root / "sub/notas.txt").stat())
    assert same_file(folder, (root / "sub").stat())


async def test_a_failed_folder_fsync_still_counts_as_written(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The file is already replaced: "cannot write" would be false, and the
    # model would write it again.
    write(root, "notas.txt", "uno\n")
    tool = write_tool(root)
    params = WriteFileParams(path="notas.txt", content="dos\n")
    tool.approval(params)
    real_fsync = os.fsync

    def fail_on_folders(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(22, "Invalid argument")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_on_folders)
    result = await tool.run(params)
    monkeypatch.undo()

    assert result == "wrote notas.txt (1 line)"
    assert (root / "notas.txt").read_text(encoding="utf-8") == "dos\n"
    assert temporaries(root) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root opens any folder")
async def test_a_folder_that_cannot_be_opened_still_counts_as_written(
    root: Path,
) -> None:
    # Writing a file needs write and search rights on its folder; opening the
    # folder for its fsync needs read rights too.
    folder = root / "dropbox"
    write(root, "dropbox/notas.txt", "uno\n")
    tool = write_tool(root)
    params = WriteFileParams(path="dropbox/notas.txt", content="dos\n")
    tool.approval(params)
    folder.chmod(0o300)
    try:
        result = await tool.run(params)
    finally:
        folder.chmod(0o755)

    assert result == "wrote dropbox/notas.txt (1 line)"
    assert (folder / "notas.txt").read_text(encoding="utf-8") == "dos\n"
