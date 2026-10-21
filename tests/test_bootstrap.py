"""`maha` end to end: configuration, adapter, `Chat` and terminal, no network."""

import json
import os
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx

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
