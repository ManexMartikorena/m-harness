"""The read-only file tools (spec hito 4, §1.6 and §4.6, and spec hito 5,
§1.6 and §4.3), in `tmp_path`."""

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
