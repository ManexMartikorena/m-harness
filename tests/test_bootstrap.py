"""`maha` end to end: configuration, adapter, `Agent` and terminal, no
network."""

import io
import json
import logging
import os
import stat
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx

from mharness import bootstrap
from mharness.adapters.cli import StdinLines
from mharness.bootstrap import main
from mharness.domain.limits import TurnLimits

KEY = "sk-test-0000000000000000"
GO_ENDPOINT = "https://opencode.ai/inference/go/openai/v1/chat/completions"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory and an XDG config home, both empty."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("OPENCODE_API_KEY", KEY)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return tmp_path


def write_user_config(workspace: Path, text: str) -> None:
    path = workspace / "xdg" / "maha" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def stdin() -> Iterator[Callable[[str], None]]:
    """Replace file descriptor 0 with a pipe that holds the given input."""
    saved = os.dup(0)

    def feed(text: str) -> None:
        read_fd, write_fd = os.pipe()
        os.write(write_fd, text.encode())
        os.close(write_fd)
        os.dup2(read_fd, 0)
        os.close(read_fd)

    yield feed
    os.dup2(saved, 0)
    os.close(saved)


def streamed(text: str, prompt_tokens: int, completion_tokens: int) -> bytes:
    """An SSE body: the text, the finish reason, the usage and [DONE]."""
    chunks = [
        {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]},
        {
            "model": "glm-5.3-flash",
            "choices": [],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        },
    ]
    events = [f"data: {json.dumps(chunk)}\n\n" for chunk in chunks]
    return ("".join(events) + "data: [DONE]\n\n").encode()


def sse_response(body: bytes) -> respx.MockResponse:
    return respx.MockResponse(
        headers={"content-type": "text/event-stream"}, content=body
    )


@respx.mock
def test_two_turns_resend_the_history(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'provider = "opencode-go"\nmodel = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[
            sse_response(streamed("Hola, Ane.", 12, 9)),
            sse_response(streamed("Te llamas Ane.", 31, 5)),
        ]
    )
    stdin("Hola, soy Ane\n¿Cómo me llamo?\n/exit\n")

    code = main([])

    out = capsys.readouterr().out
    assert code == 0
    assert "· opencode-go · glm-5.3-flash ·" in out
    assert "Hola, Ane.\n  [tokens: 12 in · 9 out · <$0.0001 · session <$0.0001]" in out
    assert (
        "Te llamas Ane.\n  [tokens: 31 in · 5 out · <$0.0001 · session <$0.0001]" in out
    )

    first, second = (json.loads(call.request.content) for call in route.calls)
    assert len(first["messages"]) == 1
    assert second["messages"] == [
        {"role": "user", "content": "Hola, soy Ane"},
        {"role": "assistant", "content": "Hola, Ane."},
        {"role": "user", "content": "¿Cómo me llamo?"},
    ]
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {KEY}"


async def cut_after(body: bytes) -> AsyncIterator[bytes]:
    yield body
    raise httpx.ReadError("connection reset")


@respx.mock
def test_a_cut_stream_shows_the_error_and_the_next_turn_works(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'provider = "opencode-go"\nmodel = "glm-5.3-flash"\n')
    partial = b'data: {"choices":[{"delta":{"content":"Hola, A"}}]}\n\n'
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[
            respx.MockResponse(
                headers={"content-type": "text/event-stream"},
                content=cut_after(partial),
            ),
            sse_response(streamed("Hola, Ane.", 12, 9)),
        ]
    )
    stdin("Hola, soy Ane\nHola otra vez\n/exit\n")

    code = main([])

    captured = capsys.readouterr()
    assert code == 0
    assert (
        "> Hola, A\n> Hola, Ane.\n"
        "  [tokens: 12 in · 9 out · <$0.0001 · session <$0.0001]"
    ) in captured.out
    assert captured.err.startswith("error: the connection to the provider failed")
    # The cut turn was not kept.
    second = json.loads(route.calls.last.request.content)
    assert second["messages"] == [{"role": "user", "content": "Hola otra vez"}]


@respx.mock
def test_maha_offers_the_seven_tools(
    workspace: Path, stdin: Callable[[str], None]
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Hola.", 1, 1))
    )
    stdin("Hola\n")

    main([])

    tools = json.loads(route.calls.last.request.content)["tools"]
    assert [tool["function"]["name"] for tool in tools] == [
        "read_file",
        "list_dir",
        "glob",
        "grep",
        "write_file",
        "edit_file",
        "run_command",
    ]


def tool_call_stream(name: str, arguments: str) -> bytes:
    """An SSE body where the model asks for one tool call."""
    call = {
        "index": 0,
        "id": "call_e2e",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }
    chunks = [
        {"choices": [{"delta": {"tool_calls": [call]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 200, "completion_tokens": 20}},
    ]
    events = [f"data: {json.dumps(chunk)}\n\n" for chunk in chunks]
    return ("".join(events) + "data: [DONE]\n\n").encode()


@respx.mock
def test_a_tool_call_reads_a_real_file(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    (Path.cwd() / "notas.txt").write_text("Comprar pan\n", encoding="utf-8")
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[
            sse_response(tool_call_stream("read_file", '{"path": "notas.txt"}')),
            sse_response(streamed("Dice: comprar pan.", 230, 9)),
        ]
    )
    stdin("¿Qué dice notas.txt?\n/exit\n")

    code = main([])

    out = capsys.readouterr().out
    assert code == 0
    assert '  → read_file(path="notas.txt")\n  ✓ 1 line\n' in out
    assert (
        "Dice: comprar pan.\n"
        "  [tokens: 430 in · 29 out · 1 call · $0.0001 · session $0.0001]"
    ) in out
    second = json.loads(route.calls.last.request.content)["messages"]
    assert second[-1] == {
        "role": "tool",
        "tool_call_id": "call_e2e",
        "content": "     1\tComprar pan",
    }


def test_without_configuration_explains_what_is_missing(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([])

    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("error: no model configured.")
    assert "config.toml" in err


def test_without_key_names_the_variable(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.delenv("OPENCODE_API_KEY")

    code = main([])

    assert code == 1
    assert "OPENCODE_API_KEY is not set" in capsys.readouterr().err


def test_project_with_providers_refuses_to_start(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    project_config = Path.cwd() / ".maha" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(
        '[providers.evil]\nbase_url = "https://attacker.example.test/v1"\n',
        encoding="utf-8",
    )

    code = main([])

    assert code == 1
    assert "a project cannot declare [providers]" in capsys.readouterr().err


def test_a_broken_user_catalog_refuses_to_start(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    catalog = workspace / "xdg" / "maha" / "models.toml"
    catalog.write_text('[models."ollama/x"]\ninput = 0.1\n', encoding="utf-8")

    code = main([])

    err = capsys.readouterr().err
    assert code == 1
    assert f"invalid model catalog in {catalog}" in err
    assert "input and output go together" in err


def test_version_needs_no_configuration(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--version"])

    assert code == 0
    assert capsys.readouterr().out.startswith("maha ")


@respx.mock
def test_without_a_terminal_a_write_is_denied_without_asking(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Spec hito 5, §1.10 and §4.8: the next line of the file could "approve".
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    arguments = '{"path": "notas.txt", "content": "y"}'
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[
            sse_response(tool_call_stream("write_file", arguments)),
            sse_response(streamed("Vale.", 1, 1)),
        ]
    )
    stdin("Escribe notas.txt\ny\n/exit\n")

    code = main([])

    out = capsys.readouterr().out
    assert code == 0
    # The "y" was not an answer: it reached the model as the next message.
    last = json.loads(route.calls.last.request.content)["messages"][-1]
    assert last == {"role": "user", "content": "y"}
    assert "  (denied: input is not a terminal)\n" in out
    assert "  [denied: tell maha how to continue]\n" in out
    assert "Allow?" not in out
    assert not (Path.cwd() / "notas.txt").exists()


@pytest.fixture
def terminal() -> Iterator[Callable[[str], None]]:
    """Replace file descriptor 0 with a pseudo-terminal holding the input."""
    saved = os.dup(0)
    master, slave = os.openpty()
    os.dup2(slave, 0)
    os.close(slave)

    def type_in(text: str) -> None:
        os.write(master, text.encode())

    yield type_in
    os.dup2(saved, 0)
    os.close(saved)
    os.close(master)


@respx.mock
def test_in_a_terminal_a_command_asks_and_runs_without_the_key(
    workspace: Path,
    terminal: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The question reads the same input as the conversation (spec
    # mejora-2026-10-23-deuda-hito-5, B3), and the command does not get the
    # key (E1). `env` is harmless.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[
            sse_response(tool_call_stream("run_command", '{"command": "env"}')),
            sse_response(streamed("Hecho.", 1, 1)),
        ]
    )
    # Typed ahead: the question drops it (spec
    # mejora-2026-10-26-deuda-pre-hito-6, A2). The answer comes after, as a
    # person seeing the question would type it.
    terminal("Ejecuta env\ny\n/exit\n")
    discard = StdinLines.discard

    def discard_then_answer(self: StdinLines) -> bool:
        dropped = discard(self)
        terminal("y\n/exit\n")
        return dropped

    monkeypatch.setattr(StdinLines, "discard", discard_then_answer)

    code = main([])

    out = capsys.readouterr().out
    assert code == 0
    assert "  (discarded typed input)\n  ┌ run: env\n" in out
    assert "  ✓ exit code 0\n" in out
    result = json.loads(route.calls.last.request.content)["messages"][-1]
    assert result["role"] == "tool"
    assert "PATH=" in result["content"]
    assert KEY not in result["content"]
    assert "OPENCODE_API_KEY" not in result["content"]


def test_sessions_go_to_the_data_home_of_the_test(
    workspace: Path,
    stdin: Callable[[str], None],
    data_home: Path,
) -> None:
    # Never into the real home (spec hito 6, §1.3).
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    with respx.mock:
        respx.post(GO_ENDPOINT).mock(return_value=sse_response(streamed("Hola.", 1, 1)))
        stdin("Hola\n/exit\n")

        assert main([]) == 0

    assert len(list((data_home / "maha" / "sessions").glob("*.jsonl"))) == 1


def test_a_turn_leaves_a_trace_with_its_cost_and_without_the_key(
    workspace: Path,
    stdin: Callable[[str], None],
    data_home: Path,
) -> None:
    # Spec hito 7, §4.8: glm-5.3-flash on Go costs 0.15 and 0.50 per million.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    with respx.mock:
        respx.post(GO_ENDPOINT).mock(
            return_value=sse_response(streamed(f"Tu clave es {KEY}", 1000, 100))
        )
        stdin(f"Repite {KEY}\n/exit\n")

        assert main([]) == 0

    [session] = (data_home / "maha" / "sessions").glob("*.jsonl")
    trace = data_home / "maha" / "traces" / session.name
    text = trace.read_text(encoding="utf-8")
    events = [json.loads(line)["event"] for line in text.splitlines()]
    assert [event["type"] for event in events] == [
        "turn_started",
        "model_call_finished",
        "turn_finished",
    ]
    # 1000 * 0.15 + 100 * 0.50, per million.
    assert events[1]["cost"] == "0.0002"
    assert KEY not in text
    assert "[redacted]" in text


@respx.mock
def test_a_second_maha_resumes_the_first_one(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Spec hito 6, §4.8: the history is read back from the disk.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[
            sse_response(streamed("Hola, Ane.", 12, 9)),
            sse_response(streamed("Te llamas Ane.", 31, 5)),
        ]
    )
    stdin("Hola, soy Ane\n/exit\n")
    assert main([]) == 0
    capsys.readouterr()

    stdin("/resume\n¿Cómo me llamo?\n/exit\n")
    assert main([]) == 0

    out = capsys.readouterr().out
    assert " · 2 messages · glm-5.3-flash]\n" in out
    assert json.loads(route.calls.last.request.content)["messages"] == [
        {"role": "user", "content": "Hola, soy Ane"},
        {"role": "assistant", "content": "Hola, Ane."},
        {"role": "user", "content": "¿Cómo me llamo?"},
    ]


# The application log (spec hito 7, §1.11).


def test_warnings_go_to_maha_log_only_for_the_user(
    workspace: Path, state_home: Path, stdin: Callable[[str], None]
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    stdin("/exit\n")

    assert main([]) == 0
    logging.getLogger("mharness.adapters.prueba").warning("cannot flush %s", "x")

    log = state_home / "maha" / "maha.log"
    assert "WARNING mharness.adapters.prueba: cannot flush x" in log.read_text(
        encoding="utf-8"
    )
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    assert stat.S_IMODE(log.parent.stat().st_mode) == 0o700


def test_starting_twice_does_not_write_each_line_twice(
    workspace: Path, state_home: Path, stdin: Callable[[str], None]
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    for _ in range(2):
        stdin("/exit\n")
        assert main([]) == 0

    logging.getLogger("mharness.prueba").warning("una vez")

    text = (state_home / "maha" / "maha.log").read_text(encoding="utf-8")
    assert text.count("una vez") == 1


def test_without_a_place_for_the_log_maha_starts_and_stays_quiet(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocker = workspace / "file"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setenv("XDG_STATE_HOME", str(blocker))
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    stdin("/exit\n")

    assert main([]) == 0
    logging.getLogger("mharness.prueba").warning("nadie lo ve")

    assert "nadie lo ve" not in capsys.readouterr().err


class DiskFull(io.StringIO):
    def write(self, text: str) -> int:
        raise OSError(28, "No space left on device")


def test_a_log_that_cannot_be_written_prints_nothing(
    workspace: Path,
    state_home: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Disk full, a read-only folder: Python would print "--- Logging error
    # ---" and the message to the terminal (final review of hito 7).
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    stdin("/exit\n")
    assert main([]) == 0
    capsys.readouterr()
    [handler] = logging.getLogger("mharness").handlers
    assert isinstance(handler, logging.StreamHandler)
    old = handler.setStream(DiskFull())
    assert old is not None
    old.close()

    logging.getLogger("mharness.prueba").warning("\x1b[2J secreto")

    assert capsys.readouterr().err == ""


def test_rotated_logs_are_only_for_the_user_too(
    workspace: Path,
    state_home: Path,
    stdin: Callable[[str], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "_LOG_BYTES", 200)
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    stdin("/exit\n")
    assert main([]) == 0
    previous = os.umask(0)
    try:
        for number in range(10):
            logging.getLogger("mharness.prueba").warning("línea %d", number)
    finally:
        os.umask(previous)

    folder = state_home / "maha"
    assert stat.S_IMODE((folder / "maha.log").stat().st_mode) == 0o600
    assert stat.S_IMODE((folder / "maha.log.1").stat().st_mode) == 0o600


def test_without_a_home_maha_says_so(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No HOME and no entry in passwd: Path.home() fails.
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(name)

    def no_home() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", no_home)

    code = main([])

    assert code == 1
    assert "cannot find your home folder" in capsys.readouterr().err


# `maha eval` end to end (spec hito 8, §1.5 to §1.9), on a battery of one
# task and with the model mocked.

ONE_TASK = """
instruction = "¿Qué versión declara pyproject.toml?"
fixture = "tienda"

[check]
answer_contains = ["1.4.2"]
file = "pyproject.toml"
contains = ['version = "1.4.2"']
"""


def battery(root: Path) -> Path:
    (root / "fixtures" / "tienda").mkdir(parents=True)
    (root / "fixtures" / "tienda" / "pyproject.toml").write_text('version = "1.4.2"\n')
    (root / "tasks" / "01-version").mkdir(parents=True)
    (root / "tasks" / "01-version" / "task.toml").write_text(ONE_TASK, encoding="utf-8")
    return root


def test_eval_saves_a_baseline_and_then_marks_a_regression(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    with respx.mock:
        respx.post(GO_ENDPOINT).mock(
            return_value=sse_response(streamed("Es la 1.4.2.", 1000, 10))
        )

        assert main(["eval", "--tasks", str(evals), "--repeat", "2", "--save"]) == 0

    out = capsys.readouterr().out
    assert "  ✓ 01-version · glm-5.3-flash #1 · 1 step ·" in out
    assert "glm-5.3-flash · no baseline yet\n" in out
    # 2 * (1000 * 0.15 + 10 * 0.50) per million, exact before rounding.
    assert "  total        2/2   100%   $0.0003 in all\n" in out
    [saved] = (evals / "baselines").glob("*.json")
    baseline = json.loads(saved.read_text())
    assert (baseline["model"], baseline["repeat"]) == ("glm-5.3-flash", 2)
    assert baseline["tasks"]["01-version"]["passes"] == 2
    # Only numbers: never what the model said.
    assert "1.4.2." not in saved.read_text()
    # The runs' sessions and traces, apart from the user's.
    runs = list((workspace / "state" / "maha" / "evals").glob("*/sessions/*.jsonl"))
    assert len(runs) == 2

    with respx.mock:
        respx.post(GO_ENDPOINT).mock(
            return_value=sse_response(streamed("No lo sé.", 1000, 10))
        )

        assert main(["eval", "--tasks", str(evals)]) == 1

    out = capsys.readouterr().out
    assert (
        "  ✗ 01-version · glm-5.3-flash #1 · the answer does not contain '1.4.2'" in out
    )
    assert "  ⚠ 01-version: passed every time in the baseline, now 0/1" in out
    # Every run in full, to look at a failure: the report shows one line.
    # By content: two `maha eval` of the same second do not sort by time.
    folders = (workspace / "state" / "maha" / "evals").iterdir()
    every = [run for f in folders for run in json.loads((f / "runs.json").read_text())]
    [failed] = [run for run in every if run["outcome"] == "fail"]
    assert (failed["outcome"], failed["detail"]) == (
        "fail",
        "the answer does not contain '1.4.2'",
    )


def test_eval_keeps_a_baseline_only_of_the_whole_battery(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')

    assert main(["eval", "--save", "--only", "01-version"]) == 1

    assert "--save keeps a baseline of the whole battery" in capsys.readouterr().err


def test_eval_names_a_task_that_does_not_exist(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    evals = battery(workspace / "evals")

    assert main(["eval", "--tasks", str(evals), "--only", "99-nope"]) == 1

    assert "error: no task '99-nope'" in capsys.readouterr().err


def test_allow_takes_the_names_of_the_tools_maha_has(tmp_path: Path) -> None:
    names = bootstrap._tools(tmp_path, {}).names()

    assert tuple(names) == bootstrap.TOOL_NAMES


# `maha -p` (spec hito 8, §1.10 and §1.11).


@respx.mock
def test_print_answers_on_stdout_and_saves_the_session(
    workspace: Path,
    stdin: Callable[[str], None],
    data_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Dos palabras.", 12, 3))
    )
    stdin("uno dos\n")

    code = main(["-p", "cuenta las palabras"])

    captured = capsys.readouterr()
    assert (code, captured.out) == (0, "Dos palabras.\n")
    assert captured.err == "  [tokens: 12 in · 3 out · <$0.0001 · session <$0.0001]\n"
    messages = json.loads(route.calls.last.request.content)["messages"]
    assert messages == [
        {
            "role": "user",
            "content": "cuenta las palabras\n\n<stdin>\nuno dos\n</stdin>",
        }
    ]
    assert len(list((data_home / "maha" / "sessions").glob("*.jsonl"))) == 1


@respx.mock
def test_print_denies_a_write_without_allow(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    arguments = '{"path": "hola.txt", "content": "hola"}'
    respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(tool_call_stream("write_file", arguments))
    )
    stdin("")

    assert main(["-p", "crea hola.txt"]) == 4

    err = capsys.readouterr().err
    assert "  ✗ error: the user denied this call\n" in err
    assert not (Path.cwd() / "hola.txt").exists()


@respx.mock
def test_print_writes_with_allow_but_never_what_runs_code(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    respx.post(GO_ENDPOINT).mock(
        side_effect=[
            sse_response(
                tool_call_stream(
                    "write_file", '{"path": "hola.txt", "content": "hola\\n"}'
                )
            ),
            sse_response(streamed("Creado.", 1, 1)),
            sse_response(
                tool_call_stream(
                    "write_file",
                    '{"path": ".github/workflows/ci.yml", "content": "on: push\\n"}',
                )
            ),
        ]
    )
    stdin("")

    assert main(["-p", "crea hola.txt", "--allow", "write_file"]) == 0
    assert main(["-p", "crea el CI", "--allow", "write_file"]) == 4

    assert (Path.cwd() / "hola.txt").read_text(encoding="utf-8") == "hola\n"
    assert not (Path.cwd() / ".github").exists()
    assert capsys.readouterr().out == "Creado.\n"


def test_print_from_a_terminal_without_text_says_how(
    workspace: Path,
    terminal: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')

    code = main(["-p"])

    captured = capsys.readouterr()
    assert (code, captured.out) == (2, "")
    assert "-p needs an instruction" in captured.err


@respx.mock
def test_print_writes_json(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    respx.post(GO_ENDPOINT).mock(return_value=sse_response(streamed("Hola.", 1, 1)))
    stdin("")

    code = main(["-p", "hola", "--output-format", "json"])

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert (code, captured.err) == (0, "")
    assert (result["result"], result["model"]) == ("Hola.", "glm-5.3-flash")


# -c, -r, -m and the limits on the command line (spec hito 8, §1.12, §1.13).


@respx.mock
def test_continue_with_print_follows_a_print_session(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[
            sse_response(streamed("Apuntado.", 1, 1)),
            sse_response(streamed("Que apuntara 42.", 1, 1)),
        ]
    )
    stdin("")
    assert main(["-p", "apunta 42"]) == 0
    capsys.readouterr()

    stdin("")
    assert main(["-c", "-p", "¿qué te pedí antes?"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "Que apuntara 42.\n"
    assert " · 2 messages · glm-5.3-flash]\n" in captured.err
    assert [
        m["content"] for m in json.loads(route.calls.last.request.content)["messages"]
    ] == [
        "apunta 42",
        "Apuntado.",
        "¿qué te pedí antes?",
    ]


@respx.mock
def test_resume_a_session_of_another_directory_with_another_model(
    workspace: Path,
    stdin: Callable[[str], None],
    data_home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[
            sse_response(streamed("Hola.", 1, 1)),
            sse_response(streamed("Sigo.", 1, 1)),
        ]
    )
    stdin("")
    assert main(["-p", "hola"]) == 0
    (saved,) = (data_home / "maha" / "sessions").glob("*.jsonl")
    elsewhere = workspace / "otro"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    capsys.readouterr()

    stdin("")
    code = main(["-r", saved.stem, "-m", "kimi-k2.7-code", "-p", "sigue"])

    err = capsys.readouterr().err
    assert code == 0
    assert (
        f"[this session was in {workspace / 'project'}; tools work in {elsewhere}]"
        in err
    )
    assert json.loads(route.calls.last.request.content)["model"] == "kimi-k2.7-code"


def test_continue_without_a_session_here_fails(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    stdin("")

    code = main(["-c", "-p", "sigue"])

    captured = capsys.readouterr()
    assert (code, captured.out) == (1, "")
    assert captured.err == "error: no session in this directory\n"


def test_resume_a_session_that_does_not_exist_fails_before_the_conversation(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    stdin("hola\n")

    code = main(["-r", "20261027-101500-ffff"])

    captured = capsys.readouterr()
    assert (code, captured.out) == (1, "")
    assert captured.err == "error: no session 20261027-101500-ffff\n"


@respx.mock
def test_model_on_the_command_line_names_a_new_session(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Hola.", 1, 1))
    )
    stdin("Hola\n/exit\n")

    assert main(["-m", "kimi-k2.7-code"]) == 0

    assert "· opencode-go · kimi-k2.7-code ·" in capsys.readouterr().out
    assert json.loads(route.calls.last.request.content)["model"] == "kimi-k2.7-code"


@respx.mock
def test_the_limits_of_the_command_line_win(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n[limits]\nmax_steps = 25\n')
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(tool_call_stream("list_dir", "{}"))
    )
    stdin("")

    assert main(["-p", "mira", "--max-steps", "1"]) == 3

    assert len(route.calls) == 1
    assert "  [step limit reached: 1]\n" in capsys.readouterr().err


@respx.mock
def test_the_command_line_can_loosen_a_limit_of_the_configuration(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n[limits]\nmax_steps = 1\n')
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[
            sse_response(tool_call_stream("list_dir", "{}")),
            sse_response(streamed("Vacío.", 1, 1)),
        ]
    )
    stdin("")

    main(["-p", "mira", "--max-steps", "2"])

    assert len(route.calls) == 2
    assert capsys.readouterr().out == "Vacío.\n"


def test_every_limit_of_the_turn_has_its_option() -> None:
    assert tuple(TurnLimits.model_fields) == bootstrap._LIMITS


def busy() -> respx.MockResponse:
    # Retry-After: 0, so that the retries do not wait.
    return respx.MockResponse(429, headers={"Retry-After": "0"})


@respx.mock
def test_a_busy_provider_is_retried_and_then_the_fallback_answers(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(
        workspace, 'model = "glm-5.3-flash"\nfallback_model = "glm-5.3"\n'
    )
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[busy()] * 4 + [sse_response(streamed("Hola.", 1, 1))]
    )
    stdin("")

    assert main(["-p", "Hola"]) == 0

    models = [json.loads(call.request.content)["model"] for call in route.calls]
    assert models == ["glm-5.3-flash"] * 4 + ["glm-5.3"]
    assert capsys.readouterr().out == "Hola.\n"


@respx.mock
def test_the_fallback_model_of_the_command_line_wins(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(
        workspace, 'model = "glm-5.3-flash"\nfallback_model = "glm-5.3"\n'
    )
    route = respx.post(GO_ENDPOINT).mock(
        side_effect=[busy()] * 4 + [sse_response(streamed("Hola.", 1, 1))]
    )
    stdin("")

    main(["-p", "Hola", "--fallback-model", "kimi-k2.7-code"])

    assert json.loads(route.calls.last.request.content)["model"] == "kimi-k2.7-code"


@respx.mock
def test_without_a_fallback_the_last_error_ends_the_run(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(side_effect=[busy()] * 4)
    stdin("")

    assert main(["-p", "Hola"]) == 1

    assert len(route.calls) == 4
    assert "error: HTTP 429" in capsys.readouterr().err


def test_models_lists_the_catalog_of_the_configured_provider(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')

    assert main(["models"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("model ")
    assert "\nglm-5.3-flash " in out
    assert "of opencode-go · prices per million tokens" in out
