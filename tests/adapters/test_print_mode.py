"""`maha -p` in the terminal: what goes to stdout and stderr, and the exit
code (spec hito 8, §1.10, §1.11 and §1.4)."""

import asyncio
import io
import signal
from collections.abc import AsyncGenerator

import pytest

from mharness.adapters.cli.headless import MAX_INPUT, print_mode
from mharness.adapters.cli.input import InputTooLarge, ReadAll
from mharness.application.agent import Agent
from mharness.application.sessions import Sessions
from mharness.application.tools import ToolRegistry
from mharness.domain.approval import ApprovalRequest
from mharness.domain.errors import ModelAuthError
from mharness.domain.events import ModelEvent
from mharness.domain.messages import ToolCallBlock
from mharness.domain.model import ModelRequest, Usage
from tests.adapters.test_conversation import KNOWN
from tests.fakes.approval import FakeApproval
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import FakeModelClient, reply, tool_calls
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
) -> tuple[int, str, str]:
    out = io.StringIO() if out is None else out
    err = io.StringIO()
    code = await print_mode(
        where,
        prompt,
        read_all=read_all,
        catalog=catalog,
        provider="opencode-go",
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
            ApprovalRequest(tool="echo", title="echo Hola", detail="", scope=None)
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
