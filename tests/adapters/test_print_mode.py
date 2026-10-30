"""`maha -p` in the terminal: what goes to stdout and stderr, and the exit
code (spec hito 8, §1.10, §1.11 and §1.4)."""

import asyncio
import io
import json
import signal
from collections.abc import AsyncGenerator
from typing import get_args

import pytest

from mharness.adapters.cli.app import OUTPUT_FORMATS
from mharness.adapters.cli.headless import (
    MAX_INPUT,
    OutputFormat,
    exit_code,
    print_mode,
)
from mharness.adapters.cli.input import InputTooLarge, ReadAll
from mharness.application.agent import Agent
from mharness.application.headless import Reason, RunResult
from mharness.application.sessions import Sessions, Start
from mharness.application.tools import ToolRegistry
from mharness.domain.approval import ApprovalRequest
from mharness.domain.errors import ModelAuthError, ModelUnavailableError
from mharness.domain.events import ModelEvent
from mharness.domain.messages import ToolCallBlock
from mharness.domain.model import ModelRequest, Usage
from mharness.domain.retry import RetryPolicy
from mharness.domain.session import is_session_id
from tests.adapters.test_conversation import KNOWN
from tests.fakes.approval import FakeApproval
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import FAKE_MODEL, FakeModelClient, reply, tool_calls
from tests.fakes.sessions import MemorySessionStore
from tests.fakes.tools import FakeTool
from tests.fakes.tracing import MemoryTraceSink

ECHO = ToolCallBlock(id="c1", name="echo", arguments='{"text": "Hola"}')


class Terminal(io.StringIO):
    """A stdout that is a terminal."""

    def isatty(self) -> bool:
        return True


def sessions(
    fake: FakeModelClient,
    *,
    tools: list[FakeTool] | None = None,
    gate: FakeApproval | None = None,
    store: MemorySessionStore | None = None,
) -> Sessions:
    registry = ToolRegistry(tools or [])

    def new_agent(model: str, history: object) -> Agent:
        return Agent(
            fake,
            registry,
            gate=gate or FakeApproval(),
            model=model,
            catalog=MemoryCatalog(),
            provider="opencode-go",
        )

    return Sessions(
        store or MemorySessionStore(),
        new_agent,
        cwd="/home/ana/proyecto",
        provider="opencode-go",
        model="glm-5.3-flash",
        version="0.8.0",
        traces=MemoryTraceSink(),
    )


def piped(text: str) -> ReadAll:
    async def read_all(limit: int) -> str:
        assert limit == MAX_INPUT
        return text

    return read_all


async def run(
    where: Sessions,
    prompt: str,
    *,
    read_all: ReadAll | None = None,
    out: io.StringIO | None = None,
    catalog: MemoryCatalog = KNOWN,
    output_format: OutputFormat = "text",
) -> tuple[int, str, str]:
    out = io.StringIO() if out is None else out
    err = io.StringIO()
    code = await print_mode(
        where,
        prompt,
        read_all=read_all,
        catalog=catalog,
        provider="opencode-go",
        output_format=output_format,
        out=out,
        err=err,
    )
    return code, out.getvalue(), err.getvalue()


async def test_stdout_has_only_the_final_answer() -> None:
    fake = FakeModelClient(
        [
            tool_calls(ECHO, text="Voy a mirar."),
            reply("Hay dos ficheros.", usage=Usage(input_tokens=12, output_tokens=9)),
        ]
    )

    code, out, err = await run(sessions(fake, tools=[FakeTool()]), "¿Qué hay?")

    assert code == 0
    assert out == "Hay dos ficheros.\n"
    assert err == (
        '  → echo(text="Hola")\n  ✓ 10 chars\n  [tokens: 12 in · 9 out · 1 call]\n'
    )


async def test_the_session_is_saved_and_can_be_resumed() -> None:
    store = MemorySessionStore()
    where = sessions(FakeModelClient([reply("Hecho.")]), store=store)

    await run(where, "Hazlo")

    (saved,) = store.sessions.values()
    assert saved.header.cwd == "/home/ana/proyecto"
    assert store.locked == set()


async def test_what_is_piped_goes_below_the_text() -> None:
    fake = FakeModelClient([reply("Dos palabras.")])

    code, out, _ = await run(
        sessions(fake), "cuenta las palabras", read_all=piped("uno dos\n")
    )

    assert (code, out) == (0, "Dos palabras.\n")
    (request,) = fake.requests
    assert request.messages[0].text == (
        "cuenta las palabras\n\n<stdin>\nuno dos\n</stdin>"
    )


async def test_without_text_what_is_piped_is_the_instruction() -> None:
    fake = FakeModelClient([reply("Hola.")])

    await run(sessions(fake), "", read_all=piped("di hola\n"))

    assert fake.requests[0].messages[0].text == "di hola\n"


@pytest.mark.parametrize(("prompt", "given"), [("", None), (" ", "\n\n")])
async def test_without_an_instruction_it_is_a_usage_error(
    prompt: str, given: str | None
) -> None:
    fake = FakeModelClient([])
    store = MemorySessionStore()

    code, out, err = await run(
        sessions(fake, store=store),
        prompt,
        read_all=None if given is None else piped(given),
    )

    assert (code, out) == (2, "")
    assert err == 'error: -p needs an instruction: maha -p "…", or pipe it to maha -p\n'
    assert fake.requests == []
    assert store.sessions == {}


async def test_too_much_input_is_an_error() -> None:
    async def huge(limit: int) -> str:
        raise InputTooLarge("the input is larger than 10 MB")

    fake = FakeModelClient([])

    code, out, err = await run(sessions(fake), "resume", read_all=huge)

    assert (code, out, err) == (1, "", "error: the input is larger than 10 MB\n")
    assert fake.requests == []


async def test_a_model_error_goes_to_stderr_with_1() -> None:
    fake = FakeModelClient([ModelAuthError("HTTP 401: Invalid key")])

    code, out, err = await run(sessions(fake), "Hola")

    assert (code, out) == (1, "")
    assert err == "error: HTTP 401: Invalid key\n"


async def test_to_a_terminal_the_answer_is_clean_and_to_a_pipe_as_written() -> None:
    answer = "rojo: \x1b[31mX\x1b[0m"

    _, to_pipe, _ = await run(sessions(FakeModelClient([reply(answer)])), "Hola")
    _, to_terminal, _ = await run(
        sessions(FakeModelClient([reply(answer)])), "Hola", out=Terminal()
    )

    assert to_pipe == answer + "\n"
    assert to_terminal == "rojo: \\x1b[31mX\\x1b[0m\n"


async def test_an_answer_that_ends_in_a_newline_gets_no_other() -> None:
    _, out, _ = await run(sessions(FakeModelClient([reply("Hola.\n")])), "Hola")

    assert out == "Hola.\n"


async def test_a_denial_says_what_allows_it() -> None:
    effect = FakeTool(
        permission="effect",
        requests=[
            ApprovalRequest(tool="echo", title="echo Hola", detail="", scope="echo")
        ],
    )
    fake = FakeModelClient([tool_calls(ECHO, text="Lo escribo.")])

    _, out, err = await run(
        sessions(fake, tools=[effect], gate=FakeApproval(["deny"])), "Escribe"
    )

    assert out == "Lo escribo.\n"
    assert "  [denied: --allow TOOL lets a tool run in this directory]\n" in err


async def test_the_catalog_notes_go_to_stderr() -> None:
    fake = FakeModelClient([reply("Hola.")])

    _, out, err = await run(sessions(fake), "Hola", catalog=MemoryCatalog())

    assert out == "Hola.\n"
    assert err.startswith("  [model not in the catalog")


async def test_a_bug_is_said_and_ends_with_1() -> None:
    class Broken(FakeModelClient):
        async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelEvent]:
            raise RuntimeError("boom")
            yield

    store = MemorySessionStore()

    code, out, err = await run(sessions(Broken([]), store=store), "Hola")

    assert (code, out) == (1, "")
    assert err == "error: internal: RuntimeError: boom\n"
    assert store.locked == set()


class Signalling(FakeModelClient):
    """Sends `number` to maha when it is called, and waits."""

    def __init__(self, number: signal.Signals) -> None:
        super().__init__([])
        self._number = number

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelEvent]:
        self.requests.append(request)
        signal.raise_signal(self._number)
        await asyncio.Event().wait()
        raise AssertionError("not cancelled")
        yield


@pytest.mark.parametrize(
    ("number", "code"),
    [(signal.SIGINT, 130), (signal.SIGTERM, 143), (signal.SIGHUP, 129)],
)
async def test_a_signal_ends_with_128_plus_it(
    number: signal.Signals, code: int
) -> None:
    fake = Signalling(number)
    store = MemorySessionStore()

    result, out, err = await run(sessions(fake, store=store), "Hola")

    assert (result, out) == (code, "")
    assert err == "  [interrupted]\n"
    assert len(fake.requests) == 1
    assert store.locked == set()


async def test_a_signal_while_reading_the_input_ends_too() -> None:
    fake = FakeModelClient([])

    async def never(limit: int) -> str:
        signal.raise_signal(signal.SIGINT)
        await asyncio.Event().wait()
        raise AssertionError("not cancelled")

    code, out, err = await run(sessions(fake), "", read_all=never)

    assert (code, out, err) == (130, "", "")
    assert fake.requests == []


# --output-format json and stream-json (spec hito 8, §1.11).


async def test_json_is_one_object_with_stable_names() -> None:
    fake = FakeModelClient(
        [
            tool_calls(ECHO, text="Voy a mirar."),
            reply("Hay dos.", usage=Usage(input_tokens=12, output_tokens=9)),
        ]
    )

    code, out, err = await run(
        sessions(fake, tools=[FakeTool()]),
        "¿Qué hay?",
        output_format="json",
        catalog=MemoryCatalog(),
    )

    assert (code, err) == (0, "")
    assert out.count("\n") == 1
    result = json.loads(out)
    assert result.pop("duration_s") >= 0
    assert result == {
        "type": "result",
        "session_id": result["session_id"],
        "result": "Hay dos.",
        "reason": "end_turn",
        "is_error": False,
        "steps": 2,
        "tool_calls": 1,
        "tool_errors": 0,
        "denials": [],
        "usage": {
            "input_tokens": 12,
            "output_tokens": 9,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
        },
        "cost_usd": None,
        # The one that answered, as the provider names it.
        "model": FAKE_MODEL,
        "error": None,
    }
    assert is_session_id(result["session_id"])


async def test_json_tells_the_error_and_its_cost_as_a_string() -> None:
    fake = FakeModelClient([ModelAuthError("HTTP 401: Invalid key")])

    code, out, err = await run(sessions(fake), "Hola", output_format="json")

    result = json.loads(out)
    assert (code, err) == (1, "")
    assert (result["reason"], result["is_error"]) == ("error", True)
    assert (result["error"], result["cost_usd"]) == ("HTTP 401: Invalid key", "0")


async def test_json_escapes_what_a_terminal_would_run() -> None:
    answer = "rojo: \x1b[31mX \u202e"

    _, out, _ = await run(
        sessions(FakeModelClient([reply(answer)])), "Hola", output_format="json"
    )

    assert "\x1b" not in out
    assert "\u202e" not in out
    assert json.loads(out)["result"] == answer


async def test_stream_json_is_one_event_per_line_and_the_result_last() -> None:
    fake = FakeModelClient([tool_calls(ECHO), reply("Hola.")])

    code, out, err = await run(
        sessions(fake, tools=[FakeTool()]), "Hola", output_format="stream-json"
    )

    lines = [json.loads(line) for line in out.splitlines()]
    assert (code, err) == (0, "")
    assert [line["type"] for line in lines] == [
        "turn_started",
        "model_call_finished",
        "tool_call_proposed",
        "tool_finished",
        "text_delta",
        "text_delta",
        "model_call_finished",
        "turn_finished",
        "result",
    ]
    assert lines[0]["text"] == "Hola"
    assert lines[-1]["result"] == "Hola."


async def test_a_tool_that_crashes_is_told_on_stderr_in_json_too() -> None:
    class Broken(FakeTool):
        def summary(self, result: str) -> str:
            raise RuntimeError("boom")

    fake = FakeModelClient([tool_calls(ECHO), reply("Vaya.")])

    code, out, err = await run(
        sessions(fake, tools=[Broken()]), "Hola", output_format="json"
    )

    assert (code, json.loads(out)["result"]) == (0, "Vaya.")
    assert err.startswith('warning: tool "echo" failed: summary: RuntimeError: boom\n')


def test_the_formats_of_the_command_line_are_those_of_the_output() -> None:
    assert get_args(OutputFormat.__value__) == OUTPUT_FORMATS


# Resuming at the start (spec hito 8, §1.12).


async def test_a_resumed_session_is_told_on_stderr_only_in_text() -> None:
    store = MemorySessionStore()
    await run(sessions(FakeModelClient([reply("Apuntado.")]), store=store), "apunta")
    (first,) = store.sessions

    code, out, err = await print_mode_resuming(store, first, "text")
    assert (code, out) == (0, "Hecho.\n")
    assert err.startswith(f"  [resumed {first} · 2 messages · glm-5.3-flash]\n")

    code, out, err = await print_mode_resuming(store, first, "json")
    assert (code, err) == (0, "")
    assert json.loads(out)["session_id"] == first


async def print_mode_resuming(
    store: MemorySessionStore, session: str, output_format: OutputFormat
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = await print_mode(
        sessions(FakeModelClient([reply("Hecho.")]), store=store),
        "sigue",
        read_all=None,
        catalog=KNOWN,
        provider="opencode-go",
        output_format=output_format,
        start=Start(session=session),
        out=out,
        err=err,
    )
    return code, out.getvalue(), err.getvalue()


async def test_a_session_that_cannot_be_resumed_is_an_error() -> None:
    fake = FakeModelClient([])
    err = io.StringIO()

    code = await print_mode(
        sessions(fake),
        "sigue",
        read_all=None,
        catalog=KNOWN,
        provider="opencode-go",
        start=Start(last=True),
        out=io.StringIO(),
        err=err,
    )

    assert (code, err.getvalue()) == (1, "error: no session in this directory\n")
    assert fake.requests == []


# Exit codes (spec hito 8, §1.4).


def ended(reason: Reason) -> RunResult:
    return RunResult(
        session="20261027-101500-3fa2",
        text="",
        reason=reason,
        steps=1,
        tool_calls=0,
        tool_errors=0,
        denials=[],
        usage=Usage(),
        cost=None,
        duration=0,
        model="m",
        error=None,
    )


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        ("end_turn", 0),
        ("error", 1),
        ("max_steps", 3),
        ("max_cost", 3),
        ("max_tokens", 3),
        ("timeout", 3),
        ("denied", 4),
    ],
)
def test_each_way_a_turn_ends_has_its_code(reason: Reason, code: int) -> None:
    assert exit_code(ended(reason)) == code


def test_every_way_a_turn_ends_is_in_the_table_above() -> None:
    assert len(get_args(Reason.__value__)) == 7


class ClosedPipe(io.StringIO):
    """A stdout whose reader went away (`maha -p … | head -1`)."""

    def write(self, text: str) -> int:
        raise BrokenPipeError(32, "Broken pipe")


@pytest.mark.parametrize("output_format", ["text", "json", "stream-json"])
async def test_a_reader_that_goes_away_ends_quietly_with_1(
    output_format: OutputFormat,
) -> None:
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Hola.")])

    code, _, err = await run(
        sessions(fake, store=store),
        "Hola",
        out=ClosedPipe(),
        output_format=output_format,
    )

    assert (code, err) == (1, "")
    assert store.locked == set()


async def test_a_denial_without_scope_says_it_needs_a_person() -> None:
    # A secret, outside the directory or a file that runs code: --allow
    # does not change it (spec hito 8, §1.2), and the note must not say so.
    secret = FakeTool(
        requests=[
            ApprovalRequest(tool="echo", title="read .env", detail="", scope=None)
        ]
    )
    fake = FakeModelClient([tool_calls(ECHO)])

    _, _, err = await run(
        sessions(fake, tools=[secret], gate=FakeApproval(["deny"])), "Lee .env"
    )

    assert (
        "  [denied: never without a person: outside this directory, a secret "
        "or a file that runs code]\n"
    ) in err
    assert "--allow" not in err


async def no_wait(seconds: float) -> None:
    """A `sleep` that does not sleep."""


def retrying(fake: FakeModelClient) -> Sessions:
    """Sessions whose agents retry once, without waiting, and fall back."""

    def new_agent(model: str, history: object) -> Agent:
        return Agent(
            fake,
            ToolRegistry([]),
            gate=FakeApproval(),
            model=model,
            catalog=MemoryCatalog(),
            provider="opencode-go",
            retry=RetryPolicy(max_retries=1, random=lambda: 0.0),
            sleep=no_wait,
            fallback="glm-5.3",
        )

    return Sessions(
        MemorySessionStore(),
        new_agent,
        cwd="/home/ana/proyecto",
        provider="opencode-go",
        model="glm-5.3-flash",
        version="0.8.0",
        traces=MemoryTraceSink(),
    )


DOWN = ModelUnavailableError("HTTP 503")


async def test_in_text_a_retry_and_a_fallback_go_to_stderr() -> None:
    fake = FakeModelClient([DOWN, DOWN, reply("Hola.")])

    code, out, err = await run(retrying(fake), "Hola")

    assert (code, out) == (0, "Hola.\n")
    assert err.startswith(
        "  [glm-5.3-flash: HTTP 503; retrying in 1 s (1/1)]\n"
        "  [glm-5.3-flash keeps failing (HTTP 503); glm-5.3 goes on]\n"
    )


async def test_stream_json_has_the_retry_and_the_fallback() -> None:
    fake = FakeModelClient([DOWN, DOWN, reply("Hola.")])

    code, out, err = await run(retrying(fake), "Hola", output_format="stream-json")

    lines = [json.loads(line) for line in out.splitlines()]
    assert (code, err) == (0, "")
    assert lines[1] == {
        "type": "model_retry",
        "model": "glm-5.3-flash",
        "attempt": 1,
        "max_retries": 1,
        "delay": 1.0,
        "error": "HTTP 503",
    }
    assert lines[2] == {
        "type": "model_fallback",
        "model": "glm-5.3-flash",
        "fallback": "glm-5.3",
        "error": "HTTP 503",
    }
