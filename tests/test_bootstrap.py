"""`maha` end to end: configuration, adapter, `Agent` and terminal, no
network."""

import json
import os
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx

from mharness.adapters.cli import StdinLines
from mharness.bootstrap import main

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
    assert "Hola, Ane.\n  [tokens: 12 in · 9 out]" in out
    assert "Te llamas Ane.\n  [tokens: 31 in · 5 out]" in out

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
    assert "> Hola, A\n> Hola, Ane.\n  [tokens: 12 in · 9 out]" in captured.out
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
    assert "Dice: comprar pan.\n  [tokens: 430 in · 29 out · 1 call]" in out
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
