"""The file tools (spec hito 4, §1.6 and §4.6, and spec hito 5, §1.6 to §1.8,
§4.3 and §4.4), in `tmp_path`."""

import asyncio
import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from mharness.adapters.tools import (
    EditFile,
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
    EditFileParams,
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
    # Decision D8: what run() would refuse is refused before asking, if the
    # metadata tells it; a binary file waits for the approval (review of
    # PR 2, fix 1).
    workspace = Workspace(root)

    with pytest.raises(ToolError, match="file not found"):
        ReadFile(workspace).approval(ReadFileParams(path="../missing"))
    with pytest.raises(ToolError, match="is a directory"):
        ReadFile(workspace).approval(ReadFileParams(path="../other"))
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


# edit_file (spec hito 5, §1.8 and §4.4.2)

NOT_FOUND = "old_string not found in {}; read the file and copy the text exactly"


def edit_tool(root: Path) -> EditFile:
    return EditFile(Workspace(root))


def edit_params(path: str, old: str, new: str, **flags: bool) -> EditFileParams:
    return EditFileParams(path=path, old_string=old, new_string=new, **flags)


def ask_edit(tool: EditFile, params: EditFileParams) -> ApprovalRequest:
    request = tool.approval(params)
    assert request is not None
    return request


async def edit(root: Path, params: EditFileParams) -> tuple[ApprovalRequest, str]:
    """Ask and run, as the loop does after a "yes"."""
    tool = edit_tool(root)
    request = ask_edit(tool, params)
    return request, await tool.run(params)


def test_edit_file_satisfies_the_port(root: Path) -> None:
    # mypy checks this assignment against the Protocol.
    tool: Tool[EditFileParams] = edit_tool(root)

    assert (tool.name, tool.permission) == ("edit_file", "effect")
    # The exact description of spec hito 5, §3.2.
    assert tool.description == (
        "Replace an exact text in a file. old_string must appear exactly once "
        "(or use replace_all). Read the file first. The user approves it. "
        'Example: {"path": "app.py", "old_string": "return 1", '
        '"new_string": "return 2"}'
    )


def test_edit_file_params_describe_each_field() -> None:
    # Decision 12.
    fields = EditFileParams.model_fields

    assert {name: field.description for name, field in fields.items()} == {
        "path": "Path relative to the working directory",
        "old_string": "The exact text to replace",
        "new_string": "The text to put in its place",
        "replace_all": "Replace every occurrence of old_string",
    }
    assert fields["replace_all"].default is False


async def test_editing_asks_with_a_diff_and_edits(root: Path) -> None:
    # No read_file before: the exact old_string is enough (spec §1.8).
    write(root, "src/app.py", "def f():\n    x = 0\n    return 1\n")
    params = edit_params("src/app.py", "return 1", "return 2")

    request, result = await edit(root, params)

    assert request == ApprovalRequest(
        tool="edit_file",
        title="edit src/app.py",
        detail="@@ -1,3 +1,3 @@\n def f():\n     x = 0\n-    return 1\n+    return 2",
        scope="edit_file",
    )
    assert result == "edited src/app.py (1 replacement)"
    assert edit_tool(root).summary(result) == "1 replacement"
    assert (root / "src/app.py").read_text(encoding="utf-8") == (
        "def f():\n    x = 0\n    return 2\n"
    )


def test_old_string_not_found_fails_before_asking(root: Path) -> None:
    # Decision 1.
    write(root, "app.py", "return 1\n")

    with pytest.raises(ToolError) as caught:
        edit_tool(root).approval(edit_params("app.py", "return 3", "return 2"))
    assert str(caught.value) == NOT_FOUND.format("app.py")


def test_old_string_twice_fails_before_asking(root: Path) -> None:
    # Decision 2.
    write(root, "app.py", "x = 1\ny = 1\nz = 1\n")

    with pytest.raises(ToolError) as caught:
        edit_tool(root).approval(edit_params("app.py", "= 1", "= 2"))
    assert str(caught.value) == (
        "old_string appears 3 times in app.py; "
        "add context to make it unique or use replace_all"
    )


async def test_replace_all_replaces_every_occurrence(root: Path) -> None:
    # Decision 3: the plural of _count.
    write(root, "app.py", "x = 1\ny = 1\nz = 1\n")
    params = edit_params("app.py", "= 1", "= 2", replace_all=True)

    request, result = await edit(root, params)

    assert request.detail == (
        "@@ -1,3 +1,3 @@\n-x = 1\n-y = 1\n-z = 1\n+x = 2\n+y = 2\n+z = 2"
    )
    assert result == "edited app.py (3 replacements)"
    assert edit_tool(root).summary(result) == "3 replacements"
    assert (root / "app.py").read_text(encoding="utf-8") == "x = 2\ny = 2\nz = 2\n"


async def test_replace_all_with_one_occurrence(root: Path) -> None:
    write(root, "app.py", "x = 1\n")

    _, result = await edit(root, edit_params("app.py", "1", "2", replace_all=True))

    assert result == "edited app.py (1 replacement)"


def test_replace_all_with_no_occurrence_fails(root: Path) -> None:
    # Decision 5.
    write(root, "app.py", "x = 1\n")

    with pytest.raises(ToolError) as caught:
        edit_tool(root).approval(edit_params("app.py", "9", "2", replace_all=True))
    assert str(caught.value) == NOT_FOUND.format("app.py")


async def test_occurrences_do_not_overlap(root: Path) -> None:
    # Decision 10: counted as str.count does, the same as str.replace.
    write(root, "a.txt", "aaa\n")

    _, result = await edit(root, edit_params("a.txt", "aa", "b"))

    assert result == "edited a.txt (1 replacement)"
    assert (root / "a.txt").read_text(encoding="utf-8") == "ba\n"


async def test_crlf_is_kept(root: Path) -> None:
    write(root, "win.txt", "")
    (root / "win.txt").write_bytes(b"uno\r\ndos\r\ntres\r\n")

    request, _ = await edit(root, edit_params("win.txt", "dos", "DOS"))

    assert request.detail == "@@ -1,3 +1,3 @@\n uno\n-dos\n+DOS\n tres"
    assert (root / "win.txt").read_bytes() == b"uno\r\nDOS\r\ntres\r\n"


def test_an_edited_file_must_be_utf8_text(root: Path) -> None:
    # Decision 7, as write_file (W2).
    (root / "img.bin").write_bytes(b"\x89PNG\0\0")
    (root / "latin1.txt").write_bytes(b"caf\xe9\n")
    tool = edit_tool(root)

    with pytest.raises(ToolError, match=r"binary file, not writable: img\.bin"):
        tool.approval(edit_params("img.bin", "PNG", "png"))
    with pytest.raises(ToolError, match=r"not a UTF-8 text file: latin1\.txt"):
        tool.approval(edit_params("latin1.txt", "caf", "té"))
    assert (root / "latin1.txt").read_bytes() == b"caf\xe9\n"


def test_the_same_strings_are_nothing_to_change(root: Path) -> None:
    write(root, "app.py", "return 1\n")

    with pytest.raises(ToolError, match="nothing to change"):
        edit_tool(root).approval(edit_params("app.py", "return 1", "return 1"))


def test_an_empty_old_string_fails(root: Path) -> None:
    # Decision 4: creating a file is for write_file.
    write(root, "app.py", "return 1\n")

    with pytest.raises(ToolError, match="old_string is empty"):
        edit_tool(root).approval(edit_params("app.py", "", "x"))


def test_a_missing_file_is_not_found(root: Path) -> None:
    # Decision 6.
    with pytest.raises(ToolError, match=r"file not found: nada\.py"):
        edit_tool(root).approval(edit_params("nada.py", "a", "b"))


def test_new_string_must_be_valid_utf8(root: Path) -> None:
    # Decision 8.
    write(root, "app.py", "return 1\n")

    with pytest.raises(ToolError, match="new_string is not valid UTF-8"):
        edit_tool(root).approval(edit_params("app.py", "1", "\ud800"))


def test_the_strings_are_checked_before_the_disk(root: Path) -> None:
    # Decision 11: the parameters first, then the file, then the question.
    (root / "src").mkdir()
    tool = edit_tool(root)

    with pytest.raises(ToolError, match="old_string is empty"):
        tool.approval(edit_params("nada.py", "", ""))
    with pytest.raises(ToolError, match="nothing to change"):
        tool.approval(edit_params("nada.py", "a", "a"))
    with pytest.raises(ToolError, match="new_string is not valid UTF-8"):
        tool.approval(edit_params("nada.py", "a", "\ud800"))
    with pytest.raises(ToolError, match="is a directory: src"):
        tool.approval(edit_params("src", "a", "b"))
    write(root, "notas.txt", "")
    with pytest.raises(ToolError, match=r"not a directory: notas\.txt"):
        tool.approval(edit_params("notas.txt/x.py", "a", "b"))


@pytest.mark.parametrize(
    ("path", "scope", "warning"),
    [
        ("notas.txt", "edit_file", None),
        ("../fuera.txt", None, OUTSIDE),
        (".env", None, SECRET_FILE),
        ("../.env", None, f"{OUTSIDE}; {SECRET_FILE}"),
    ],
)
def test_edit_scope_inside_and_none_outside_or_secret(
    root: Path, path: str, scope: str | None, warning: str | None
) -> None:
    write(root, path, "uno\n")

    request = ask_edit(edit_tool(root), edit_params(path, "uno", "dos"))

    assert (request.scope, request.warning) == (scope, warning)


async def test_an_edit_link_shows_its_target_and_is_kept(root: Path) -> None:
    # Decision W7, as write_file.
    write(root, "real.txt", "uno\n")
    (root / "notes.txt").symlink_to(root / "real.txt")

    request, result = await edit(root, edit_params("notes.txt", "uno", "dos"))

    assert request.title == "edit real.txt"
    assert request.detail == "(asked: notes.txt)\n@@ -1 +1 @@\n-uno\n+dos"
    assert result == "edited real.txt (1 replacement)"
    assert (root / "notes.txt").is_symlink()
    assert (root / "real.txt").read_text(encoding="utf-8") == "dos\n"


async def test_a_long_edit_diff_is_cut_at_60_lines(root: Path) -> None:
    write(root, "big.txt", "".join(f"old {i}\n" for i in range(100)))
    params = edit_params("big.txt", "old", "new", replace_all=True)

    lines = ask_edit(edit_tool(root), params).detail.splitlines()

    assert len(lines) == 61
    assert lines[0] == "@@ -1,100 +1,100 @@"
    assert lines[-1] == "… [141 more diff lines]"


async def test_a_failed_edit_cannot_write(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Decision A2, as write_file.
    write(root, "app.py", "return 1\n")
    tool = edit_tool(root)
    params = edit_params("app.py", "1", "2")
    tool.approval(params)

    def fail(*args: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(ToolError) as caught:
        await tool.run(params)
    monkeypatch.undo()

    assert str(caught.value) == "cannot write app.py: No space left on device"
    assert (root / "app.py").read_text(encoding="utf-8") == "return 1\n"
    assert temporaries(root) == []


# edit_file: what was shown is what is written (spec §10; decisions D1, W6)


async def test_a_file_changed_after_the_question_is_not_edited(root: Path) -> None:
    write(root, "app.py", "return 1\n")
    tool = edit_tool(root)
    params = edit_params("app.py", "return 1", "return 2")

    tool.approval(params)
    write(root, "app.py", "# yours\nreturn 1\n")

    with pytest.raises(ToolError, match=r"app\.py changed after the question"):
        await tool.run(params)
    assert (root / "app.py").read_text(encoding="utf-8") == "# yours\nreturn 1\n"


async def test_a_file_removed_after_the_question_is_not_edited(root: Path) -> None:
    write(root, "app.py", "return 1\n")
    tool = edit_tool(root)
    params = edit_params("app.py", "return 1", "return 2")

    tool.approval(params)
    (root / "app.py").unlink()

    with pytest.raises(ToolError, match=r"app\.py changed after the question"):
        await tool.run(params)
    assert not (root / "app.py").exists()


async def test_an_edit_link_changed_after_the_question_is_not_followed(
    root: Path,
) -> None:
    write(root, "a.txt", "uno\n")
    write(root, "b.txt", "uno\n")
    link = root / "link.txt"
    link.symlink_to(root / "a.txt")
    tool = edit_tool(root)
    params = edit_params("link.txt", "uno", "dos")

    tool.approval(params)
    link.unlink()
    link.symlink_to(root / "b.txt")

    with pytest.raises(ToolError, match=r"link\.txt changed after the question"):
        await tool.run(params)
    assert (root / "b.txt").read_text(encoding="utf-8") == "uno\n"


async def test_editing_without_a_question_is_refused(root: Path) -> None:
    write(root, "app.py", "return 1\n")
    tool = edit_tool(root)
    params = edit_params("app.py", "1", "2")

    with pytest.raises(ToolError, match="changed after the question"):
        await tool.run(params)
    tool.approval(params)
    write(root, "otro.py", "return 1\n")
    tool.approval(edit_params("otro.py", "1", "2"))
    with pytest.raises(ToolError, match="changed after the question"):
        await tool.run(params)
    assert (root / "app.py").read_text(encoding="utf-8") == "return 1\n"


# edit_file: an old_string with "\n" in a CRLF file (decision 9b)


def crlf(root: Path, name: str, text: bytes) -> Path:
    path = root / name
    path.write_bytes(text)
    return path


async def test_a_multiline_old_string_is_adapted_to_crlf(root: Path) -> None:
    path = crlf(root, "win.txt", b"uno\r\ndos\r\ntres\r\n")
    params = edit_params("win.txt", "uno\ndos\n", "UNO\nDOS\nmas\n")

    request, result = await edit(root, params)

    # The diff and the result show what is written.
    assert request.detail == "@@ -1,3 +1,4 @@\n-uno\n-dos\n+UNO\n+DOS\n+mas\n tres"
    assert result == "edited win.txt (1 replacement)"
    assert path.read_bytes() == b"UNO\r\nDOS\r\nmas\r\ntres\r\n"


async def test_an_exact_match_comes_before_the_crlf_one(root: Path) -> None:
    # One "a\nb" exact, one "a\r\nb": the exact one alone, with no
    # "appears 2 times".
    path = crlf(root, "mixed.txt", b"a\nb\r\na\r\nb\r\n")

    _, result = await edit(root, edit_params("mixed.txt", "a\nb", "x\ny"))

    assert result == "edited mixed.txt (1 replacement)"
    assert path.read_bytes() == b"x\ny\r\na\r\nb\r\n"


async def test_an_lf_file_is_not_adapted(root: Path) -> None:
    path = write(root, "unix.txt", "uno\ndos\n")
    tool = edit_tool(root)

    with pytest.raises(ToolError) as caught:
        tool.approval(edit_params("unix.txt", "uno\r\ndos", "x"))
    assert str(caught.value) == NOT_FOUND.format("unix.txt")
    _, result = await edit(root, edit_params("unix.txt", "uno\ndos", "UNO\nDOS"))
    assert result == "edited unix.txt (1 replacement)"
    assert path.read_bytes() == b"UNO\nDOS\n"


def test_uniqueness_counts_the_crlf_matches(root: Path) -> None:
    crlf(root, "win.txt", b"a\r\nb\r\na\r\nb\r\n")

    with pytest.raises(ToolError) as caught:
        edit_tool(root).approval(edit_params("win.txt", "a\nb", "x\ny"))
    assert str(caught.value) == (
        "old_string appears 2 times in win.txt; "
        "add context to make it unique or use replace_all"
    )


async def test_replace_all_counts_the_crlf_matches(root: Path) -> None:
    path = crlf(root, "win.txt", b"a\r\nb\r\na\r\nb\r\n")
    params = edit_params("win.txt", "a\nb", "x\ny", replace_all=True)

    _, result = await edit(root, params)

    assert result == "edited win.txt (2 replacements)"
    assert path.read_bytes() == b"x\r\ny\r\nx\r\ny\r\n"


async def test_only_the_lone_lf_of_new_string_change(root: Path) -> None:
    # "\r\n" in new_string stays as it is; a lone "\n" becomes "\r\n".
    path = crlf(root, "win.txt", b"uno\r\ndos\r\n")
    params = edit_params("win.txt", "uno\ndos", "a\r\nb\nc")

    await edit(root, params)

    assert path.read_bytes() == b"a\r\nb\r\nc\r\n"


def test_a_crlf_old_string_still_not_found_fails(root: Path) -> None:
    crlf(root, "win.txt", b"uno\r\ndos\r\n")

    with pytest.raises(ToolError) as caught:
        edit_tool(root).approval(edit_params("win.txt", "uno\ntres", "x"))
    assert str(caught.value) == NOT_FOUND.format("win.txt")


def test_an_edit_that_leaves_the_text_equal_is_nothing_to_change(
    root: Path,
) -> None:
    # Decision C: "a\n" adapted is "a\r\n", the same as new_string; the text
    # would not change, so there is nothing to ask.
    path = crlf(root, "win.txt", b"a\r\nb\r\n")

    with pytest.raises(ToolError, match="nothing to change"):
        edit_tool(root).approval(edit_params("win.txt", "a\n", "a\r\n"))
    assert path.read_bytes() == b"a\r\nb\r\n"


def test_a_mixed_file_old_string_across_lf_and_crlf_is_not_found(
    root: Path,
) -> None:
    # Case A1: neither exact ("b\n" is "b\r\n") nor adapted ("a\r\n" is "a\n").
    crlf(root, "mixed.txt", b"a\nb\r\nc\r\n")

    with pytest.raises(ToolError) as caught:
        edit_tool(root).approval(edit_params("mixed.txt", "a\nb\n", "X\n"))
    assert str(caught.value) == NOT_FOUND.format("mixed.txt")


async def test_a_mixed_file_edits_only_its_crlf_part(root: Path) -> None:
    # Case A2: the LF part keeps its "\n".
    path = crlf(root, "mixed.txt", b"a\nb\r\nc\r\n")

    _, result = await edit(root, edit_params("mixed.txt", "b\nc", "B\nC"))

    assert result == "edited mixed.txt (1 replacement)"
    assert path.read_bytes() == b"a\nB\r\nC\r\n"


async def test_an_old_string_with_crlf_and_lone_lf_is_adapted(root: Path) -> None:
    # Case B: only the lone "\n" changes; its "\r\n" stays.
    path = crlf(root, "win.txt", b"a\r\nb\r\nc\r\n")

    _, result = await edit(root, edit_params("win.txt", "a\r\nb\nc", "x\ny"))

    assert result == "edited win.txt (1 replacement)"
    assert path.read_bytes() == b"x\r\ny\r\n"


# With a warning, nothing that depends on the content is told to the model
# before the user approves (review of PR 2, fix 1).


@pytest.mark.parametrize("path", [".env", "../x.txt"])
async def test_an_edit_with_a_warning_asks_before_saying_not_found(
    root: Path, path: str
) -> None:
    write(root, path, "uno\n")
    tool = edit_tool(root)
    params = edit_params(path, "tres", "cuatro")

    request = ask_edit(tool, params)

    assert request.scope is None
    strings = "old_string:\ntres\nnew_string:\ncuatro"
    asked = "" if path == ".env" else f"(asked: {path})\n"
    assert request.detail == f"{asked}{strings}"
    with pytest.raises(ToolError) as caught:
        await tool.run(params)
    assert str(caught.value) == NOT_FOUND.format(path)
    assert (root / path).read_text(encoding="utf-8") == "uno\n"


@pytest.mark.parametrize(
    ("text", "old", "new", "error"),
    [
        ("a\na\n", "a", "b", "old_string appears 2 times in .env"),
        ("a\r\nb\r\n", "a\n", "a\r\n", "nothing to change"),
    ],
)
async def test_other_content_errors_of_an_edit_wait_for_the_approval(
    root: Path, text: str, old: str, new: str, error: str
) -> None:
    path = crlf(root, ".env", text.encode())
    tool = edit_tool(root)
    params = edit_params(".env", old, new)

    assert ask_edit(tool, params).warning == SECRET_FILE
    with pytest.raises(ToolError, match=error):
        await tool.run(params)
    assert path.read_bytes() == text.encode()


async def test_replace_all_shows_in_the_strings_of_an_edit(root: Path) -> None:
    write(root, ".env", "uno\n")
    params = edit_params(".env", "a\nb", "c", replace_all=True)

    detail = ask_edit(edit_tool(root), params).detail

    assert detail == "old_string:\na\nb\nnew_string:\nc\nreplace_all: true"


async def test_a_write_with_a_warning_asks_before_nothing_to_change(
    root: Path,
) -> None:
    write(root, ".env", "KEY=1\n")
    tool = write_tool(root)
    params = WriteFileParams(path=".env", content="KEY=1\n")

    request = ask_write(tool, ".env", "KEY=1\n")

    assert (request.title, request.detail) == ("overwrite .env", "KEY=1")
    with pytest.raises(ToolError, match="nothing to change"):
        await tool.run(params)


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"\x89PNG\0\0", r"binary file, not writable: \.\./img"),
        (b"caf\xe9\n", r"not a UTF-8 text file: \.\./img"),
    ],
)
async def test_a_file_that_is_not_text_outside_asks_first(
    root: Path, data: bytes, error: str
) -> None:
    (root.parent / "img").write_bytes(data)
    write_params = WriteFileParams(path="../img", content="x\n")
    edit_call = edit_params("../img", "caf", "té")
    writer, editor = write_tool(root), edit_tool(root)

    asked = "(asked: ../img)\n"
    assert ask_write(writer, "../img", "x\n").detail == f"{asked}x"
    assert ask_edit(editor, edit_call).detail == (
        f"{asked}old_string:\ncaf\nnew_string:\nté"
    )
    with pytest.raises(ToolError, match=error):
        await writer.run(write_params)
    with pytest.raises(ToolError, match=error):
        await editor.run(edit_call)
    assert (root.parent / "img").read_bytes() == data


async def test_a_valid_edit_with_a_warning_still_shows_the_diff(root: Path) -> None:
    # The diff goes to the user, not to the model.
    write(root, ".env", "KEY=1\n")

    request, _ = await edit(root, edit_params(".env", "1", "2"))

    assert request.detail == "@@ -1 +1 @@\n-KEY=1\n+KEY=2"


def test_metadata_errors_with_a_warning_still_come_first(root: Path) -> None:
    (root.parent / "dir").mkdir()
    tool = edit_tool(root)

    with pytest.raises(ToolError, match=r"file not found: \.env"):
        tool.approval(edit_params(".env", "a", "b"))
    with pytest.raises(ToolError, match=r"is a directory: \.\./dir"):
        tool.approval(edit_params("../dir", "a", "b"))
    with pytest.raises(ToolError, match="old_string is empty"):
        tool.approval(edit_params(".env", "", "b"))
    with pytest.raises(ToolError, match="content is not valid UTF-8"):
        write_tool(root).approval(WriteFileParams(path=".env", content="\ud800"))


async def test_a_binary_file_outside_asks_before_read_file_says_so(
    root: Path,
) -> None:
    (root.parent / "img").write_bytes(b"\x89PNG\0\0")
    tool = ReadFile(Workspace(root))
    params = ReadFileParams(path="../img")

    assert tool.approval(params) is not None
    with pytest.raises(ToolError, match=r"binary file, not readable: \.\./img"):
        await tool.run(params)


# The size of the file to change (review of PR 2, fix 2)


def big_file(root: Path, name: str) -> Path:
    """3 MiB without writing them: a sparse file."""
    path = root / name
    path.touch()
    os.truncate(path, 3 * 1024 * 1024)
    return path


@pytest.mark.parametrize("name", ["big.txt", ".env"])
def test_a_file_too_large_is_refused_before_reading(
    root: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    # The size is metadata: also with a warning, before asking.
    big_file(root, name)

    def no_reading(*args: object) -> bytes:
        raise AssertionError("read a file too large")

    monkeypatch.setattr(Path, "read_bytes", no_reading)
    with pytest.raises(ToolError) as edited:
        edit_tool(root).approval(edit_params(name, "a", "b"))
    with pytest.raises(ToolError) as written:
        write_tool(root).approval(WriteFileParams(path=name, content="x"))

    assert str(edited.value) == (
        "file too large to edit (3.0 MiB, max 2 MiB); use run_command"
    )
    assert str(written.value) == (
        "file too large to overwrite (3.0 MiB, max 2 MiB); use run_command"
    )


async def test_a_file_grown_after_the_question_is_not_read(
    root: Path,
) -> None:
    path = write(root, "app.py", "return 1\n")
    tool = edit_tool(root)
    params = edit_params("app.py", "1", "2")
    tool.approval(params)

    os.truncate(path, 3 * 1024 * 1024)

    with pytest.raises(ToolError, match="file too large to edit"):
        await tool.run(params)


# A file that cannot be read (review of PR 2, fix 3)

not_root = pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")


@pytest.fixture
def locked(root: Path) -> Iterator[Path]:
    """A file and a folder without read rights; restored at the end."""
    file = write(root, "locked.txt", "x\n")
    folder = root / "closed"
    folder.mkdir()
    file.chmod(0)
    folder.chmod(0)
    yield root
    file.chmod(0o644)
    folder.chmod(0o755)


DENIED = "Permission denied"


@not_root
async def test_reading_tools_say_cannot_read(locked: Path) -> None:
    workspace = Workspace(locked)

    with pytest.raises(ToolError) as read_error:
        await ReadFile(workspace).run(ReadFileParams(path="locked.txt"))
    with pytest.raises(ToolError) as list_error:
        await ListDir(workspace).run(ListDirParams(path="closed"))
    with pytest.raises(ToolError) as grep_file:
        await Grep(workspace).run(GrepParams(pattern="x", path="locked.txt"))

    assert str(read_error.value) == f"cannot read locked.txt: {DENIED}"
    assert str(list_error.value) == f"cannot read closed: {DENIED}"
    assert str(grep_file.value) == f"cannot read locked.txt: {DENIED}"


@not_root
async def test_grep_skips_the_files_it_cannot_read_when_walking(
    locked: Path,
) -> None:
    # As secrets, binary and large files (review of PR 2, fix 8).
    write(locked, "ok.txt", "x\n")

    result = await Grep(Workspace(locked)).run(GrepParams(pattern="x"))

    assert result == "ok.txt:1: x"


@not_root
def test_changing_tools_say_cannot_read(locked: Path) -> None:
    with pytest.raises(ToolError) as edited:
        edit_tool(locked).approval(edit_params("locked.txt", "x", "y"))
    with pytest.raises(ToolError) as written:
        write_tool(locked).approval(WriteFileParams(path="locked.txt", content="y"))

    assert str(edited.value) == f"cannot read locked.txt: {DENIED}"
    assert str(written.value) == f"cannot read locked.txt: {DENIED}"


@not_root
async def test_a_file_locked_after_the_question_cannot_be_read(root: Path) -> None:
    path = write(root, "app.py", "return 1\n")
    tool = edit_tool(root)
    params = edit_params("app.py", "1", "2")
    tool.approval(params)

    path.chmod(0)
    try:
        with pytest.raises(ToolError, match=f"cannot read app.py: {DENIED}"):
            await tool.run(params)
    finally:
        path.chmod(0o644)


# run() runs only the exact call that was asked (review of PR 2, fix 5)


async def test_a_write_with_other_content_than_asked_is_refused(root: Path) -> None:
    tool = write_tool(root)
    tool.approval(WriteFileParams(path="notas.txt", content="uno\n"))

    with pytest.raises(ToolError, match=r"notas\.txt changed after the question"):
        await tool.run(WriteFileParams(path="notas.txt", content="otro\n"))
    assert not (root / "notas.txt").exists()


@pytest.mark.parametrize(
    "other",
    [
        edit_params("app.py", "return 1", "return 3"),
        edit_params("app.py", "1", "2"),
        edit_params("app.py", "return 1", "return 2", replace_all=True),
    ],
)
async def test_an_edit_with_other_strings_than_asked_is_refused(
    root: Path, other: EditFileParams
) -> None:
    write(root, "app.py", "return 1\n")
    tool = edit_tool(root)
    tool.approval(edit_params("app.py", "return 1", "return 2"))

    with pytest.raises(ToolError, match=r"app\.py changed after the question"):
        await tool.run(other)
    assert (root / "app.py").read_text(encoding="utf-8") == "return 1\n"


async def test_a_search_with_other_parameters_than_asked_is_refused(
    root: Path, other: Path
) -> None:
    workspace = Workspace(root)
    grep, glob, read = Grep(workspace), Glob(workspace), ReadFile(workspace)
    grep.approval(GrepParams(pattern="x", path="../other"))
    glob.approval(GlobParams(pattern="*.py", path="../other"))
    read.approval(ReadFileParams(path="../other/a.py"))

    with pytest.raises(ToolError, match="changed after the question"):
        await grep.run(GrepParams(pattern="password", path="../other"))
    with pytest.raises(ToolError, match="changed after the question"):
        await glob.run(GlobParams(pattern="*", path="../other"))
    with pytest.raises(ToolError, match="changed after the question"):
        await read.run(ReadFileParams(path="../other/a.py", offset=2))


# Changing .git always asks (review of PR 2, fix 6)

GIT_DIR = "git directory: hooks and config here can run code"


@pytest.mark.parametrize(
    ("path", "for_session", "warning"),
    [
        (".git/hooks/pre-commit", False, GIT_DIR),
        (".git/config", False, GIT_DIR),
        ("src/x.py", True, None),
        ("../repo/.git/config", False, f"{OUTSIDE}; {GIT_DIR}"),
    ],
)
def test_changing_git_is_never_for_the_session(
    root: Path, path: str, for_session: bool, warning: str | None
) -> None:
    write(root, path, "uno\n")

    written = ask_write(write_tool(root), path, "dos\n")
    edited = ask_edit(edit_tool(root), edit_params(path, "uno", "dos"))

    assert written.scope == ("write_file" if for_session else None)
    assert edited.scope == ("edit_file" if for_session else None)
    assert written.warning == edited.warning == warning


def test_a_link_into_git_is_never_for_the_session(root: Path) -> None:
    write(root, ".git/hooks/pre-commit", "uno\n")
    (root / "hook").symlink_to(root / ".git/hooks/pre-commit")

    request = ask_write(write_tool(root), "hook", "dos\n")

    assert (request.scope, request.warning) == (None, GIT_DIR)


def test_reading_git_does_not_ask(root: Path) -> None:
    write(root, ".git/config", "[core]\n")

    assert (
        ReadFile(Workspace(root)).approval(ReadFileParams(path=".git/config")) is None
    )


# The diff tells when the line endings change (review of PR 2, fix 4)


def endings_note(root: Path, old: bytes, new: str) -> str:
    (root / "n.txt").write_bytes(old)
    return ask_write(write_tool(root), "n.txt", new).detail


@pytest.mark.parametrize(
    ("old", "new", "first"),
    [
        (b"a\r\nb\r\n", "a\nc\n", "(line endings change: CRLF → LF)"),
        (b"a\nb\n", "a\r\nc\r\n", "(line endings change: LF → CRLF)"),
        (b"a\nb\r\n", "a\nc\n", "(line endings change: mixed → LF)"),
        (b"a\r\nb\r\n", "a\r\nc\n", "(line endings change: CRLF → mixed)"),
        (b"a\rb\r", "a\nc\n", "(line endings change: mixed → LF)"),
    ],
)
def test_a_change_of_line_endings_is_told_first(
    root: Path, old: bytes, new: str, first: str
) -> None:
    lines = endings_note(root, old, new).splitlines()

    assert lines[0] == first
    assert lines[1].startswith("@@ ")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"a", "b\r\n"),  # no endings before
        (b"a\r\n", "b"),  # no endings after
        (b"a\r\nb\r\n", "a\r\nc\r\n"),  # the same style
    ],
)
def test_no_note_without_two_different_styles(root: Path, old: bytes, new: str) -> None:
    assert endings_note(root, old, new).startswith("@@ ")


def test_only_line_endings_have_no_extra_note(root: Path) -> None:
    assert endings_note(root, b"a\r\nb\r\n", "a\nb\n") == "(only line endings change)"


def test_the_note_goes_after_the_asked_path(root: Path) -> None:
    write(root, "real.txt", "uno\n")
    (root / "notes.txt").symlink_to(root / "real.txt")

    detail = ask_write(write_tool(root), "notes.txt", "dos\r\n").detail

    assert detail.splitlines()[:3] == [
        "(asked: notes.txt)",
        "(line endings change: LF → CRLF)",
        "@@ -1 +1 @@",
    ]


def test_an_edit_tells_a_change_of_line_endings(root: Path) -> None:
    write(root, "app.py", "x\n")

    request = ask_edit(edit_tool(root), edit_params("app.py", "x\n", "y\r\n"))

    assert request.detail == "(line endings change: LF → CRLF)\n@@ -1 +1 @@\n-x\n+y"


def test_the_fallback_detail_has_no_note(root: Path) -> None:
    # Fix 1: the fallback derives nothing from the content.
    write(root, ".env", "KEY=1\n")

    request = ask_edit(edit_tool(root), edit_params(".env", "nada", "x\r\n"))

    assert request.detail == "old_string:\nnada\nnew_string:\nx"


def test_a_failed_stat_of_the_file_to_change_cannot_be_read(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fix 3 also covers the size check (second review of PR 2).
    write(root, "app.py", "return 1\n")
    edit = edit_tool(root)
    overwrite = write_tool(root)
    real_stat = Path.stat

    def failing_stat(self: Path, **kwargs: bool) -> os.stat_result:
        if self.name == "app.py" and not kwargs:
            raise OSError(5, "Input/output error")
        return real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", failing_stat)
    with pytest.raises(ToolError) as edited:
        edit.approval(edit_params("app.py", "1", "2"))
    with pytest.raises(ToolError) as written:
        overwrite.approval(WriteFileParams(path="app.py", content="x"))
    monkeypatch.undo()

    assert str(edited.value) == "cannot read app.py: Input/output error"
    assert str(written.value) == "cannot read app.py: Input/output error"
