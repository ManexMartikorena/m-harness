"""`maha` end to end: configuration, adapter, `Agent` and terminal, no
network."""

import asyncio
import contextlib
import errno
import io
import json
import logging
import os
import re
import signal
import stat
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from mharness import bootstrap, config
from mharness.adapters.catalog import TomlCatalog
from mharness.adapters.cli import StdinLines, TerminalApproval
from mharness.bootstrap import _eval_prompt, _eval_tools, _prompt, _tools, main
from mharness.domain.evals import TaskRun
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


def conversation(body: bytes) -> list[dict[str, Any]]:
    """The messages of a request, after its system prompt, which goes first
    in every one (spec hito 10)."""
    messages: list[dict[str, Any]] = json.loads(body)["messages"]
    system, *rest = messages
    assert system["role"] == "system"
    assert "You are maha" in str(system["content"])
    return rest


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
def test_the_projects_agents_md_reaches_the_model(
    workspace: Path, stdin: Callable[[str], None], capsys: pytest.CaptureFixture[str]
) -> None:
    # Spec hito 10, §1.4: what the project tells its agents, in every call.
    write_user_config(workspace, 'provider = "opencode-go"\nmodel = "glm-5.3-flash"\n')
    (workspace / "project" / "AGENTS.md").write_text(
        "Los tests: `uv run pytest`.\n", encoding="utf-8"
    )
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Vale.", 12, 3))
    )
    stdin("Hola\n/exit\n")

    assert main([]) == 0

    # Said at the start: nothing enters the prompt unseen (§1.8).
    assert "  [instructions: AGENTS.md]\n" in capsys.readouterr().out
    system = json.loads(last_turn(route))["messages"][0]
    assert system["role"] == "system"
    assert (
        '<instructions source="AGENTS.md">\n'
        "Los tests: `uv run pytest`.\n</instructions>" in system["content"]
    )
    assert f"Working directory: {workspace / 'project'}" in system["content"]


@respx.mock
def test_print_says_the_instructions_on_stderr(
    workspace: Path, stdin: Callable[[str], None], capsys: pytest.CaptureFixture[str]
) -> None:
    write_user_config(workspace, 'provider = "opencode-go"\nmodel = "glm-5.3-flash"\n')
    (workspace / "project" / "CLAUDE.md").write_text("x\n", encoding="utf-8")
    respx.post(GO_ENDPOINT).mock(return_value=sse_response(streamed("Vale.", 12, 3)))
    stdin("")

    assert main(["-p", "Hola"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "Vale.\n"
    assert "  [instructions: CLAUDE.md]\n" in captured.err


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

    first, second = (conversation(call.request.content) for call in route.calls)
    assert len(first) == 1
    assert second == [
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
    assert conversation(last_turn(route)) == [
        {"role": "user", "content": "Hola otra vez"}
    ]


@respx.mock
def test_maha_offers_its_tools(workspace: Path, stdin: Callable[[str], None]) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Hola.", 1, 1))
    )
    stdin("Hola\n")

    main([])

    tools = json.loads(last_turn(route))["tools"]
    assert [tool["function"]["name"] for tool in tools] == [
        "read_file",
        "list_dir",
        "glob",
        "grep",
        "write_file",
        "edit_file",
        "run_command",
        "todo_write",
    ]


def test_with_a_terminal_the_model_can_ask_the_person(
    workspace: Path, stdin: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Spec hito 10, §1.11: `ask_user` only with someone to answer.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    stdin("Hola\n")
    monkeypatch.setattr(os, "isatty", lambda fd: True)

    with respx.mock:
        route = respx.post(GO_ENDPOINT).mock(
            return_value=sse_response(streamed("Hola.", 1, 1))
        )
        main([])

    tools = json.loads(last_turn(route))["tools"]
    assert tools[-1]["function"]["name"] == "ask_user"


@respx.mock
def test_p_never_offers_ask_user(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nobody to answer, even from a terminal: the model would lose a step.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Hola.", 1, 1))
    )
    monkeypatch.setattr(os, "isatty", lambda fd: True)

    main(["-p", "Hola"])

    tools = json.loads(last_turn(route))["tools"]
    names = [tool["function"]["name"] for tool in tools]
    assert "ask_user" not in names
    assert "todo_write" in names


def turns_and_titles(
    *turns: httpx.Response,
) -> Callable[[httpx.Request], httpx.Response]:
    """Answers each turn's call with the next of `turns`, and the calls
    that write the session's title (no stream) with a title of their own."""
    left = list(turns)

    def answer(request: httpx.Request) -> httpx.Response:
        if not json.loads(request.content).get("stream"):
            return httpx.Response(
                200,
                json={
                    "model": "glm-5.3-flash",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Un título"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 3},
                },
            )
        return left.pop(0)

    return answer


def last_turn(route: respx.Route) -> bytes:
    """The body of the last call of a turn: in a conversation, the title of
    the session goes in the background, in a call of its own, without
    streaming (spec hito 10, §1.12)."""
    turns = [c for c in route.calls if json.loads(c.request.content).get("stream")]
    content: bytes = turns[-1].request.content
    return content


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
    second = conversation(last_turn(route))
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
    last = conversation(last_turn(route))[-1]
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
    # Lines that arrive together are one turn (audit after hito 10, I4):
    # what a person types comes one line at a time.
    terminal("Ejecuta env\n")
    discard = StdinLines.discard
    readline = StdinLines.readline

    def discard_then_answer(self: StdinLines) -> bool:
        dropped = discard(self)
        terminal("y\n")
        return dropped

    async def then_exit(self: StdinLines) -> str:
        line = await readline(self)
        if line == "Ejecuta env":
            # Typed while the model answers.
            terminal("y\n")
        if line == "y":
            terminal("/exit\n")
        return line

    monkeypatch.setattr(StdinLines, "discard", discard_then_answer)
    monkeypatch.setattr(StdinLines, "readline", then_exit)

    code = main([])

    out = capsys.readouterr().out
    assert code == 0
    assert "  (discarded typed input)\n  ┌ run: env\n" in out
    assert "  ✓ exit code 0\n" in out
    result = conversation(last_turn(route))[-1]
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
        # The system prompt of the session, with its first turn (spec hito
        # 10, §1.13): its fingerprint and where its layers came from.
        "prompt",
        "model_call_finished",
        "turn_finished",
    ]
    assert len(events[1]["fingerprint"]) == 12
    assert [layer["kind"] for layer in events[1]["layers"]] == ["base", "environment"]
    # 1000 * 0.15 + 100 * 0.50, per million.
    assert events[2]["cost"] == "0.0002"
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
        side_effect=turns_and_titles(
            sse_response(streamed("Hola, Ane.", 12, 9)),
            sse_response(streamed("Te llamas Ane.", 31, 5)),
        )
    )
    stdin("Hola, soy Ane\n/exit\n")
    assert main([]) == 0
    capsys.readouterr()

    stdin("/resume\n¿Cómo me llamo?\n/exit\n")
    assert main([]) == 0

    out = capsys.readouterr().out
    assert " · 2 messages · glm-5.3-flash]\n" in out
    assert conversation(last_turn(route)) == [
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

        assert main(["eval", "--tasks", str(evals), "--repeat", "5", "--save"]) == 0

    out = capsys.readouterr().out
    assert "  ✓ 01-version · glm-5.3-flash #1 · 1 step ·" in out
    assert "glm-5.3-flash · no baseline yet\n" in out
    # 5 * (1000 * 0.15 + 10 * 0.50) per million, rounded.
    assert "  total        5/5   100%   $0.0008 in all\n" in out
    [saved] = (evals / "baselines").glob("*.json")
    baseline = json.loads(saved.read_text())
    assert (baseline["model"], baseline["repeat"]) == ("glm-5.3-flash", 5)
    assert baseline["tasks"]["01-version"]["passes"] == 5
    # Only numbers: never what the model said.
    assert "1.4.2." not in saved.read_text()
    # The runs' sessions and traces, apart from the user's.
    runs = list((workspace / "state" / "maha" / "evals").glob("*/sessions/*.jsonl"))
    assert len(runs) == 5

    with respx.mock:
        respx.post(GO_ENDPOINT).mock(
            return_value=sse_response(streamed("No lo sé.", 1000, 10))
        )

        assert main(["eval", "--tasks", str(evals), "--repeat", "5"]) == 1

    out = capsys.readouterr().out
    assert (
        "  ✗ 01-version · glm-5.3-flash #1 · the answer does not contain '1.4.2'" in out
    )
    assert "  ⚠ 01-version: 5/5 in the baseline, now 0/5 (p = 0.004)" in out
    # Every run in full, to look at a failure: the report shows one line.
    # By content: two `maha eval` of the same second do not sort by time.
    folders = (workspace / "state" / "maha" / "evals").iterdir()
    every = [run for f in folders for run in json.loads((f / "runs.json").read_text())]
    failed = next(run for run in every if run["outcome"] == "fail")
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


@pytest.mark.parametrize(
    ("config", "args"),
    [
        ('model = "glm-5.3-flash"\n', ["--effort", "high"]),
        ('model = "glm-5.3-flash"\neffort = "low"\n', []),
    ],
)
def test_eval_keeps_a_baseline_only_with_the_models_own_effort(
    workspace: Path, capsys: pytest.CaptureFixture[str], config: str, args: list[str]
) -> None:
    # Spec hito 9, §5: a baseline does not say its effort, and the next ones
    # would compare against it.
    write_user_config(workspace, config)

    assert main(["eval", "--save", *args]) == 1

    assert "--save keeps a baseline with the model's own effort" in (
        capsys.readouterr().err
    )


@respx.mock
def test_eval_says_the_effort_it_runs_with(
    workspace: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Es la 1.4.2.", 10, 5))
    )

    main(["eval", "--tasks", str(evals), "--effort", "high"])

    first = capsys.readouterr().out.splitlines()[0]
    assert first.endswith(" · effort high")
    assert json.loads(last_turn(route))["reasoning_effort"] == "high"


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
    assert captured.err.startswith(
        "  [tokens: 12 in · 3 out · <$0.0001 · session <$0.0001]\n  [session "
    )
    messages = conversation(last_turn(route))
    [message] = messages
    assert message["role"] == "user"
    assert re.fullmatch(
        r"cuenta las palabras\n\n<(stdin-\w+)>\nuno dos\n</\1>", message["content"]
    )
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
    assert [m["content"] for m in conversation(last_turn(route))] == [
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
    assert json.loads(last_turn(route))["model"] == "kimi-k2.7-code"


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
    assert json.loads(last_turn(route))["model"] == "kimi-k2.7-code"


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

    assert json.loads(last_turn(route))["model"] == "kimi-k2.7-code"


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


def a_print_session(stdin: Callable[[str], None], answer: str = "Hola.") -> str:
    """Run one `maha -p` and return the id of its session."""
    respx.post(GO_ENDPOINT).mock(return_value=sse_response(streamed(answer, 1, 1)))
    stdin("")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(["-p", "Hola", "--output-format", "json"]) == 0
    session: str = json.loads(out.getvalue())["session_id"]
    return session


@respx.mock
def test_sessions_lists_and_deletes_from_the_shell(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    session = a_print_session(stdin)

    assert main(["sessions"]) == 0
    assert capsys.readouterr().out.startswith(f"* {session}  ")

    assert main(["sessions", "delete", session]) == 0
    assert capsys.readouterr().out == f"deleted {session}\n"

    assert main(["sessions"]) == 0
    assert capsys.readouterr().out == "(no sessions)\n"
    assert main(["sessions", "delete", session]) == 1


@respx.mock
def test_trace_shows_the_last_session_here_or_one_by_id(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    session = a_print_session(stdin)

    assert main(["trace"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"{session} · glm-5.3-flash · 1 turn · 1 model call")
    assert f"/maha/traces/{session}.jsonl]\n" in out

    assert main(["trace", session]) == 0
    assert capsys.readouterr().out == out


@respx.mock
def test_stats_adds_up_the_calls_of_every_session(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    a_print_session(stdin)
    a_print_session(stdin)

    assert main(["stats", "--days", "1"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["day", "model", "calls", "in", "out", "cost"]
    assert lines[1].split()[1:5] == ["glm-5.3-flash", "2", "2", "2"]
    assert lines[-1].split()[:4] == ["total", "2", "2", "2"]


def test_stats_without_traces_says_so(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')

    assert main(["stats"]) == 0

    assert capsys.readouterr().out == "(no calls to a model in the traces)\n"


@respx.mock
def test_export_writes_a_session_in_markdown_or_json(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    session = a_print_session(stdin, "Hola, Ane.")

    assert main(["export", session]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Hola\n")
    assert out.endswith("## maha\n\nHola, Ane.\n")

    assert main(["export", session, "--format", "json"]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["header"]["id"] == session


@respx.mock
def test_an_exported_session_is_imported_and_resumed(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    session = a_print_session(stdin, "Hola, Ane.")
    assert main(["export", session, "--format", "json"]) == 0
    file = workspace / "s.json"
    file.write_text(capsys.readouterr().out, encoding="utf-8")

    assert main(["import", str(file)]) == 0

    new = capsys.readouterr().out.split()[2]
    assert new != session
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Sí.", 1, 1))
    )
    stdin("")
    assert main(["-r", new, "-p", "¿Sigues?"]) == 0
    assert conversation(last_turn(route))[:2] == [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola, Ane."},
    ]


@pytest.mark.parametrize(
    "args",
    [["models"], ["sessions"], ["trace"], ["stats"], ["export", "x"]],
)
def test_commands_that_do_not_call_the_model_need_no_key(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
) -> None:
    # Found in the manual check of hito 8: `maha trace` asked for the key.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.delenv("OPENCODE_API_KEY")

    main(args)

    assert "OPENCODE_API_KEY" not in capsys.readouterr().err


@pytest.mark.parametrize("args", [["-p", "Hola"], ["eval", "--only", "01"]])
def test_what_calls_the_model_still_needs_the_key(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
    args: list[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.delenv("OPENCODE_API_KEY")
    stdin("")

    assert main(args) == 1

    assert "OPENCODE_API_KEY is not set" in capsys.readouterr().err


@respx.mock
@pytest.mark.parametrize("args", [["sessions"], ["stats"], ["models", "--all"]])
def test_commands_that_do_not_call_the_model_need_no_model(
    workspace: Path, capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    # Found in the audit of hito 8: without `model`, `maha sessions` did not
    # start. Without a configuration file at all, too.
    assert main(args) == 0

    assert "no model configured" not in capsys.readouterr().err


@respx.mock
def test_trace_and_export_without_a_model_still_work(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    session = a_print_session(stdin)
    (workspace / "xdg" / "maha" / "config.toml").write_text("", encoding="utf-8")

    assert main(["trace", session]) == 0
    assert main(["export", session]) == 0
    assert main(["sessions", "delete", session]) == 0
    assert "no model configured" not in capsys.readouterr().err


def test_what_calls_the_model_still_needs_a_model(
    workspace: Path,
    stdin: Callable[[str], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdin("")

    assert main(["-p", "Hola"]) == 1

    assert "no model configured" in capsys.readouterr().err


def test_ctrl_c_in_eval_keeps_the_runs_that_finished(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Audit of hito 8: Ctrl+C lost every run, paid calls included, behind a
    # Python traceback.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    calls = 0

    def answer(request: httpx.Request) -> respx.MockResponse:
        nonlocal calls
        calls += 1
        if calls == 2:
            # As a person pressing Ctrl+C during the second run.
            os.kill(os.getpid(), signal.SIGINT)
        return sse_response(streamed("Es la 1.4.2.", 1000, 10))

    with respx.mock:
        respx.post(GO_ENDPOINT).mock(side_effect=answer)

        code = main(["eval", "--tasks", str(evals), "--repeat", "2", "--jobs", "1"])

    assert code == 130
    err = capsys.readouterr().err
    assert "interrupted: 1 run kept in " in err
    [folder] = (workspace / "state" / "maha" / "evals").iterdir()
    [kept] = json.loads((folder / "runs.json").read_text())
    assert (kept["attempt"], kept["outcome"]) == (1, "pass")


@pytest.mark.parametrize("output_format", ["json", "stream-json"])
def test_p_in_json_without_key_still_writes_a_result(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    # Review of the audit of hito 8: an error of the configuration left
    # `| jq .result` with nothing to read.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.delenv("OPENCODE_API_KEY")

    code = main(["-p", "hola", "--output-format", output_format])

    out, err = capsys.readouterr()
    result = json.loads(out)
    assert code == 1
    assert (result["type"], result["is_error"]) == ("result", True)
    assert "OPENCODE_API_KEY is not set" in result["error"]
    assert "OPENCODE_API_KEY is not set" in err


def test_p_in_text_without_key_writes_nothing_on_stdout(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.delenv("OPENCODE_API_KEY")

    assert main(["-p", "hola"]) == 1
    assert capsys.readouterr().out == ""


@respx.mock
def test_p_with_a_model_of_an_unspoken_format_calls_nobody(
    workspace: Path,
    stdin: Callable[[str], None],
    data_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Spec hito 9, §1.2: the catalog says gpt-6-luna speaks the Responses
    # API; a 400 from the provider would not say why.
    write_user_config(workspace, 'model = "gpt-6-luna"\n')
    route = respx.post(GO_ENDPOINT)
    stdin("")

    code = main(["-p", "hola"])

    assert code == 1
    assert not route.called
    assert (
        "gpt-6-luna uses the openai-responses API, which maha does not speak yet"
        in capsys.readouterr().err
    )


@respx.mock
def test_the_effort_of_the_command_line_wins_over_the_configuration(
    workspace: Path, stdin: Callable[[str], None]
) -> None:
    # Spec hito 9, §1.7.
    write_user_config(workspace, 'model = "glm-5.3-flash"\neffort = "low"\n')
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Hola.", 1, 1))
    )
    stdin("")

    main(["-p", "Hola"])
    main(["-p", "Hola", "--effort", "high"])

    sent = [json.loads(call.request.content) for call in route.calls]
    assert [body["reasoning_effort"] for body in sent] == ["low", "high"]


GO_ANTHROPIC = "https://opencode.ai/inference/go/anthropic/v1/messages"


@respx.mock
def test_each_model_goes_to_the_url_of_its_format(
    workspace: Path, stdin: Callable[[str], None], capsys: pytest.CaptureFixture[str]
) -> None:
    # Spec hito 9, §4, test 14: OpenCode Go serves claude-haiku-5-5 in
    # Anthropic's format and glm-5.3-flash in OpenAI's.
    write_user_config(workspace, 'model = "glm-5.3-flash"\ncache_ttl = "1h"\n')
    openai = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("De GLM.", 1, 1))
    )
    claude = respx.post(GO_ANTHROPIC).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                Path(__file__).parent / "fixtures" / "anthropic" / "hello.sse"
            ).read_bytes(),
        )
    )
    stdin("")

    assert main(["-p", "Hola"]) == 0
    assert main(["-p", "Hola", "-m", "claude-haiku-5-5"]) == 0

    assert capsys.readouterr().out == "De GLM.\nHola, Ane.\n"
    assert openai.call_count == claude.call_count == 1
    request = claude.calls.last.request
    body = json.loads(request.content)
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert request.headers["anthropic-version"] == "2026-10-21"
    assert "x-opencode-session" in request.headers
    assert (body["model"], body["max_tokens"]) == ("claude-haiku-5-5", 128_000)
    assert body["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


@respx.mock
def test_eval_with_keep_says_where_the_copies_are(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Deep audit (I9): --keep kept the copies and never said where.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    (workspace / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(workspace / "tmp"))
    evals = battery(workspace / "evals")
    respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Es la 1.4.2.", 10, 5))
    )

    assert main(["eval", "--tasks", str(evals), "--keep"]) == 0

    out = capsys.readouterr().out
    [line] = [x for x in out.splitlines() if x.startswith("copies of the repos")]
    where = Path(line.removeprefix("copies of the repositories: "))
    assert where.parent == workspace / "tmp"
    [copy] = where.glob("01-version-*/tienda")
    assert (copy / "pyproject.toml").read_text() == 'version = "1.4.2"\n'


def test_eval_with_an_effort_does_not_judge_against_the_baseline(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Deep audit (I7): the baseline is of the model's own effort.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    with respx.mock:
        respx.post(GO_ENDPOINT).mock(
            return_value=sse_response(streamed("Es la 1.4.2.", 10, 5))
        )
        assert main(["eval", "--tasks", str(evals), "--repeat", "5", "--save"]) == 0
    with respx.mock:
        respx.post(GO_ENDPOINT).mock(
            return_value=sse_response(streamed("No lo sé.", 10, 5))
        )
        args = ["eval", "--tasks", str(evals), "--repeat", "5", "--effort", "high"]

        assert main(args) == 0

    out = capsys.readouterr().out
    assert "  · 01-version: 5/5 in the baseline, now 0/5 (p = 0.004)" in out
    assert "  · effort high: the baseline ran at the model's own effort" in out


def test_eval_keeps_a_baseline_only_of_five_runs_or_more(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Deep audit (I13): spec hito 8, decision 3, asks 5 runs of each task.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    evals = battery(workspace / "evals")

    assert main(["eval", "--tasks", str(evals), "--save", "--repeat", "4"]) == 1

    assert "--save keeps a baseline of 5 runs of each task or more" in (
        capsys.readouterr().err
    )
    assert not (evals / "baselines").exists()


@respx.mock
def test_eval_keeps_no_baseline_with_runs_that_ended_in_an_error(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Deep audit (I13): the runs that did not finish would be missing from it.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    respx.post(GO_ENDPOINT).mock(return_value=httpx.Response(401))

    assert main(["eval", "--tasks", str(evals), "--save", "--repeat", "5"]) == 1

    captured = capsys.readouterr()
    assert "not saved: 5 runs of glm-5.3-flash ended in an error" in captured.err
    assert not (evals / "baselines").exists()
    # What ran is kept all the same.
    [folder] = (workspace / "state" / "maha" / "evals").iterdir()
    assert len(json.loads((folder / "runs.json").read_text())) == 5


@pytest.mark.parametrize(
    ("number", "code"), [(signal.SIGTERM, 143), (signal.SIGHUP, 129)]
)
def test_closing_signals_in_eval_keep_the_runs_and_clean_up(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    number: signal.Signals,
    code: int,
) -> None:
    # Deep audit (I6): `kill` or closing the window lost runs.json and left
    # the copies behind; only Ctrl+C was handled.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    (workspace / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(workspace / "tmp"))
    evals = battery(workspace / "evals")
    calls = 0

    def answer(request: httpx.Request) -> respx.MockResponse:
        nonlocal calls
        calls += 1
        if calls == 2:
            os.kill(os.getpid(), number)
        return sse_response(streamed("Es la 1.4.2.", 1000, 10))

    with respx.mock:
        respx.post(GO_ENDPOINT).mock(side_effect=answer)

        result = main(["eval", "--tasks", str(evals), "--repeat", "2", "--jobs", "1"])

    assert result == code
    assert "interrupted: 1 run kept in " in capsys.readouterr().err
    [folder] = (workspace / "state" / "maha" / "evals").iterdir()
    [kept] = json.loads((folder / "runs.json").read_text())
    assert (kept["attempt"], kept["outcome"]) == (1, "pass")
    assert list((workspace / "tmp").iterdir()) == []
    # The handlers go with the battery: the next signal is not caught.
    assert signal.getsignal(number) in (signal.SIG_DFL, signal.default_int_handler)


def test_a_second_signal_while_the_runs_are_written_does_not_cut_them(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Review of the deep audit: it cancelled the writing of runs.json, and
    # maha ended in a traceback.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    calls = 0
    write_runs = bootstrap._write_runs

    def answer(request: httpx.Request) -> respx.MockResponse:
        nonlocal calls
        calls += 1
        if calls == 2:
            os.kill(os.getpid(), signal.SIGTERM)
        return sse_response(streamed("Es la 1.4.2.", 1000, 10))

    def writing(path: Path, runs: Sequence[TaskRun]) -> None:
        os.kill(os.getpid(), signal.SIGTERM)
        # Long enough for the loop to handle the signal meanwhile.
        time.sleep(0.2)
        write_runs(path, runs)

    monkeypatch.setattr(bootstrap, "_write_runs", writing)
    with respx.mock:
        respx.post(GO_ENDPOINT).mock(side_effect=answer)

        result = main(["eval", "--tasks", str(evals), "--repeat", "2", "--jobs", "1"])

    assert result == 143
    assert "interrupted: 1 run kept in " in capsys.readouterr().err
    [folder] = (workspace / "state" / "maha" / "evals").iterdir()
    assert len(json.loads((folder / "runs.json").read_text())) == 1


class ClosedPipe(io.StringIO):
    """A stdout nobody reads any more, as `maha eval | head` after head ends."""

    def write(self, text: str) -> int:
        raise BrokenPipeError(32, "Broken pipe")


class ClosedWindow(io.StringIO):
    """A stdout whose terminal goes while maha runs: then it is no terminal
    any more, and what it kept fails with EIO."""

    gone = False

    def isatty(self) -> bool:
        return not self.gone

    def flush(self) -> None:
        if self.gone:
            raise OSError(errno.EIO, "Input/output error")


def closing_the_window(stdout: ClosedWindow, code: int) -> Callable[..., int]:
    def dispatch(*args: object) -> int:
        stdout.gone = True
        return code

    return dispatch


class FailingDisk(io.StringIO):
    """A stdout to a file on a disk that fails: EIO, but no window."""

    def flush(self) -> None:
        raise OSError(errno.EIO, "Input/output error")


class LiveTerminal(FailingDisk):
    """stdin or stderr on a terminal whose window stays open."""

    def isatty(self) -> bool:
        return True


def test_an_eio_of_a_file_next_to_a_live_terminal_is_no_closed_window(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Final round of the third review: judged by stdout alone, an EIO of a
    # failing disk with the window open could be taken for it.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setattr(bootstrap, "_dispatch", lambda *args: 0)
    monkeypatch.setattr(sys, "stdout", FailingDisk())
    monkeypatch.setattr(sys, "stderr", LiveTerminal())

    with pytest.raises(OSError, match="Input/output error"):
        main(["sessions"])


def test_an_eio_of_a_file_is_not_a_closed_window(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Third review of the audit after hito 10: `maha export ID > usb/x.md`
    # on a failing disk ended with 0 and the output lost, without a word.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setattr(bootstrap, "_dispatch", lambda *args: 0)
    monkeypatch.setattr(sys, "stdout", FailingDisk())

    with pytest.raises(OSError, match="Input/output error"):
        main(["sessions"])


def test_a_closed_window_keeps_the_exit_code(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Third review of the audit after hito 10: the paste marks, kept by a
    # write that failed, made the last flush raise EIO; maha ended with a
    # traceback and 1 instead of 129.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    stdout = ClosedWindow()
    monkeypatch.setattr(bootstrap, "_dispatch", closing_the_window(stdout, 129))
    monkeypatch.setattr(sys, "stdout", stdout)

    assert main(["sessions"]) == 129


def test_a_closed_window_before_any_exit_code_ends_with_129(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Third review too: an EIO out of the command itself left no code, and
    # maha ended with 1 and an error nobody saw.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')

    stdout = ClosedWindow()

    def hung_up(*args: object) -> int:
        stdout.gone = True
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(bootstrap, "_dispatch", hung_up)
    monkeypatch.setattr(sys, "stdout", stdout)

    assert main(["sessions"]) == 129


@respx.mock
def test_eval_into_a_closed_pipe_still_keeps_every_run(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deep audit (I6): the broken pipe escaped from the line of the first
    # run, and runs.json was lost.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Es la 1.4.2.", 10, 5))
    )
    monkeypatch.setattr(sys, "stdout", ClosedPipe())

    main(["eval", "--tasks", str(evals), "--repeat", "2", "--jobs", "1"])

    [folder] = (workspace / "state" / "maha" / "evals").iterdir()
    assert len(json.loads((folder / "runs.json").read_text())) == 2


@respx.mock
def test_eval_keeps_its_report_next_to_the_runs(
    workspace: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Spec hito 10, §5: the report only went to the screen, and there is no
    # command to make it again from runs.json; the second pass of the evals
    # needed a `tee` not to lose it.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Es la 1.4.2.", 1000, 10))
    )

    assert main(["eval", "--tasks", str(evals), "--repeat", "2"]) == 0

    out = capsys.readouterr().out
    [folder] = (workspace / "state" / "maha" / "evals").iterdir()
    report = (folder / "report.txt").read_text(encoding="utf-8")
    assert "  total        2/2   100%" in report
    assert report == out


def test_an_interrupted_eval_keeps_the_report_it_had(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    calls = 0

    def answer(request: httpx.Request) -> respx.MockResponse:
        nonlocal calls
        calls += 1
        if calls == 2:
            os.kill(os.getpid(), signal.SIGTERM)
        return sse_response(streamed("Es la 1.4.2.", 1000, 10))

    with respx.mock:
        respx.post(GO_ENDPOINT).mock(side_effect=answer)

        result = main(["eval", "--tasks", str(evals), "--repeat", "2", "--jobs", "1"])

    assert result == 143
    capsys.readouterr()
    [folder] = (workspace / "state" / "maha" / "evals").iterdir()
    report = (folder / "report.txt").read_text(encoding="utf-8")
    assert "  ✓ 01-version · glm-5.3-flash #1 · 1 step ·" in report
    assert report.endswith("\ninterrupted: 1 run kept in " + str(folder) + "\n")


@respx.mock
def test_eval_into_a_closed_pipe_still_keeps_the_report(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(workspace / "state"))
    evals = battery(workspace / "evals")
    respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Es la 1.4.2.", 10, 5))
    )
    monkeypatch.setattr(sys, "stdout", ClosedPipe())

    main(["eval", "--tasks", str(evals), "--repeat", "2", "--jobs", "1"])

    [folder] = (workspace / "state" / "maha" / "evals").iterdir()
    report = (folder / "report.txt").read_text(encoding="utf-8")
    assert "  total        2/2   100%" in report


@respx.mock
def test_p_says_what_the_project_configuration_chose(
    workspace: Path, stdin: Callable[[str], None], capsys: pytest.CaptureFixture[str]
) -> None:
    # Deep audit after hito 9 (M4): a .maha/config.toml can raise the cost
    # (effort, cache, fallback); maha says it at start.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    (Path.cwd() / ".maha").mkdir()
    (Path.cwd() / ".maha" / "config.toml").write_text(
        'effort = "max"\ncache_ttl = "1h"\n'
    )
    respx.post(GO_ENDPOINT).mock(return_value=sse_response(streamed("Hola.", 1, 1)))
    stdin("")

    main(["-p", "Hola"])

    assert (
        "  [from .maha/config.toml: effort max, cache 1h]\n" in capsys.readouterr().err
    )


@respx.mock
def test_a_provider_of_anthropics_format_with_its_own_version(
    workspace: Path, stdin: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deep audit after hito 9 (M10): anthropic_version and cache_ttl reach
    # the wire through bootstrap, not only the adapter.
    monkeypatch.setenv("LOCAL_KEY", KEY)
    write_user_config(
        workspace,
        'provider = "local"\nmodel = "claude-x"\n'
        "[providers.local]\n"
        'api = "anthropic"\nbase_url = "https://claude.example.test/v1"\n'
        'api_key_env = "LOCAL_KEY"\nanthropic_version = "2023-06-01"\n',
    )
    route = respx.post("https://claude.example.test/v1/messages").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                Path(__file__).parent / "fixtures" / "anthropic" / "hello.sse"
            ).read_bytes(),
        )
    )
    stdin("")

    assert main(["-p", "Hola"]) == 0

    request = route.calls.last.request
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert json.loads(request.content)["cache_control"] == {"type": "ephemeral"}


# Seeing and adjusting the system prompt (spec hito 10, §1.8).


def test_maha_prompt_shows_the_prompt_without_calling_the_model(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # No key: it never calls the model.
    monkeypatch.delenv("OPENCODE_API_KEY")
    write_user_config(workspace, 'provider = "opencode-go"\nmodel = "glm-5.3-flash"\n')
    (workspace / "project" / "AGENTS.md").write_text("Usa uv.\n", encoding="utf-8")

    assert main(["prompt", "--append-system-prompt", "Sé breve."]) == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("You are maha")
    assert "- run_command: " in captured.out
    assert '<instructions source="AGENTS.md">\nUsa uv.\n</instructions>' in captured.out
    assert captured.out.endswith("Sé breve.\n")
    assert captured.err == "  [instructions: AGENTS.md]\n"


def test_maha_prompt_cleans_what_it_shows_on_a_terminal(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Audit after hito 10, I1: an AGENTS.md of a foreign repository could
    # clear the screen or write to the clipboard (OSC 52).
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    evil = "Hola\x1b]52;c;ZWNobyBoYWNr\x07\x1b[2J\n"
    (workspace / "project" / "AGENTS.md").write_text(evil, encoding="utf-8")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    assert main(["prompt"]) == 0

    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "Hola\\x1b]52;c;ZWNobyBoYWNr\\x07\\x1b[2J" in out


def test_maha_prompt_to_a_pipe_is_the_prompt_as_it_goes(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Data for a program, as with cat: what the model gets, byte for byte.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    (workspace / "project" / "AGENTS.md").write_text("a\x1b[1mb\n", encoding="utf-8")

    assert main(["prompt"]) == 0

    assert "a\x1b[1mb" in capsys.readouterr().out


@respx.mock
def test_the_users_base_and_what_is_appended_reach_the_model(
    workspace: Path, stdin: Callable[[str], None]
) -> None:
    base = workspace / "mi-base.md"
    base.write_text("Eres un asistente de pruebas.\n", encoding="utf-8")
    extra = workspace / "extra.md"
    extra.write_text("Responde en una línea.\n", encoding="utf-8")
    write_user_config(
        workspace,
        'provider = "opencode-go"\nmodel = "glm-5.3-flash"\n'
        f"system_prompt_file = {str(base)!r}\n",
    )
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Vale.", 12, 3))
    )
    stdin("")

    code = main(
        [
            "-p",
            "Hola",
            "--append-system-prompt-file",
            str(extra),
            "--append-system-prompt",
            "Fin.",
        ]
    )

    assert code == 0
    system = json.loads(last_turn(route))["messages"][0]["content"]
    assert system.startswith("Eres un asistente de pruebas.\n\n<environment>")
    assert "You are maha" not in system
    assert system.endswith("Responde en una línea.\n\nFin.")


def test_the_base_of_the_command_line_wins(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mine = workspace / "mine.md"
    mine.write_text("Configured.\n", encoding="utf-8")
    once = workspace / "once.md"
    once.write_text("Just this once.\n", encoding="utf-8")
    write_user_config(workspace, f'model = "m"\nsystem_prompt_file = {str(mine)!r}\n')

    assert main(["prompt", "--system-prompt-file", str(once)]) == 0

    assert capsys.readouterr().out.startswith("Just this once.\n")


@pytest.mark.parametrize(
    ("content", "says"),
    [(None, "cannot read it"), (b"\xff", "not UTF-8"), (b" \n", "empty")],
)
def test_a_prompt_file_that_cannot_be_used_stops_maha(
    workspace: Path,
    capsys: pytest.CaptureFixture[str],
    content: bytes | None,
    says: str,
) -> None:
    write_user_config(workspace, 'model = "m"\n')
    path = workspace / "base.md"
    if content is not None:
        path.write_bytes(content)

    assert main(["prompt", "--system-prompt-file", str(path)]) == 1

    assert says in capsys.readouterr().err


def test_the_evals_measure_maha_not_the_users_instructions(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Spec hito 10, §5 and §4, test 16: the user's AGENTS.md and the extra
    # instructions stay out; the task's own files come in.
    write_user_config(
        workspace, 'model = "glm-5.3-flash"\ninstructions = ["notas.md"]\n'
    )
    (workspace / "xdg" / "maha" / "AGENTS.md").write_text("mine", encoding="utf-8")
    task = workspace / "task"
    task.mkdir()
    (task / "AGENTS.md").write_text("the task's", encoding="utf-8")
    (task / "notas.md").write_text("extra", encoding="utf-8")
    monkeypatch.chdir(task)
    settings = config.load(cwd=task, env=os.environ)
    catalog = TomlCatalog.load(workspace / "none.toml")

    evals = asyncio.run(
        _eval_prompt(settings, catalog, task, _eval_tools(task)).build("glm-5.3-flash")
    )
    user = asyncio.run(
        _prompt(settings, catalog, task, _tools(task, {})).build("glm-5.3-flash")
    )

    assert "the task's" in evals.text
    assert "mine" not in evals.text
    assert "extra" not in evals.text
    assert "run_command" not in evals.text
    assert "Shell:" not in evals.text
    assert "mine" in user.text
    assert "extra" in user.text


@pytest.mark.parametrize("where", ["_dispatch", "load"])
def test_ctrl_c_in_any_command_ends_quietly_with_130(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    where: str,
) -> None:
    # Audit after hito 10, I2: Ctrl+C in maha sessions, trace, stats,
    # export, import or prompt, or while the conversation starts, gave a
    # traceback.
    write_user_config(workspace, 'model = "m"\n')

    def pressed(*_: object, **__: object) -> int:
        raise KeyboardInterrupt

    target = bootstrap if where == "_dispatch" else config
    monkeypatch.setattr(target, where, pressed)

    assert main(["sessions"]) == 130
    assert capsys.readouterr().err == "\n"


def test_the_question_has_no_color_when_stdout_is_not_a_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Audit after hito 10, I11: `maha > log.txt` with a terminal for input
    # wrote its escapes in the file.
    monkeypatch.setattr(os, "isatty", lambda fd: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

    gate = bootstrap._gate(StdinLines())

    assert isinstance(gate, TerminalApproval)
    assert gate._color is False


@respx.mock
def test_print_mode_expands_init(workspace: Path, stdin: Callable[[str], None]) -> None:
    # Audit after hito 10, I9: `maha -p "/init"` sent the text as it was;
    # the conversation and the evals expand it.
    write_user_config(workspace, 'model = "glm-5.3-flash"\n')
    route = respx.post(GO_ENDPOINT).mock(
        return_value=sse_response(streamed("Nada que escribir.", 12, 3))
    )
    stdin("")

    assert main(["-p", "/init usa uv"]) == 0

    sent = conversation(last_turn(route))[-1]["content"]
    assert sent.startswith("Write or improve the AGENTS.md of this project.")
    assert "<user_notes>\nusa uv\n</user_notes>" in sent
