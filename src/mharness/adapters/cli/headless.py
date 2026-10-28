"""`maha -p`: one instruction without a person (spec hito 8, §1.10, §1.11
and §1.4).

```
$ git diff | maha -p "revisa este diff" > revision.md
  → read_file(path="src/app.py")          (stderr)
  ✓ 120 lines                             (stderr)
  [tokens: 5236 in · 410 out · 1 call]    (stderr)
```

stdout gets only the final answer, so that `x=$(maha -p …)` holds just
that; the calls, the notes and the tokens go to stderr, as in the
conversation but without a spinner.
"""

import asyncio
import signal
import sys
from typing import TextIO

from mharness.adapters.cli.commands import model_note, warn_trace, warn_unsaved
from mharness.adapters.cli.conversation import (
    CLOSING,
    call_line,
    turn_note,
    usage_line,
    warn_crash,
)
from mharness.adapters.cli.input import InputTooLarge, ReadAll
from mharness.adapters.cli.text import clean
from mharness.application.headless import RunResult, instruction, run_once
from mharness.application.sessions import Conversation, Sessions
from mharness.domain.agent_events import (
    AgentEvent,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
)
from mharness.ports.catalog import ModelCatalog

# What may be piped to -p, at most: the same as Claude Code (spec §1.10).
MAX_INPUT = 10 * 1024 * 1024

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


async def print_mode(
    sessions: Sessions,
    prompt: str,
    *,
    read_all: ReadAll | None,
    catalog: ModelCatalog,
    provider: str,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run `prompt`, with what `read_all` gives below it, in a new session;
    return the exit code. `read_all` is None when the input is a terminal.

    Ctrl+C and the closing signals end it as they end the conversation:
    what ran is saved, and the code is 128 + the signal.
    """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    assert task is not None
    received: list[int] = []

    def on_signal(number: int) -> None:
        received.append(number)
        task.cancel()

    for number in (signal.SIGINT, *CLOSING):
        loop.add_signal_handler(number, on_signal, number)
    try:
        return await _print(sessions, prompt, read_all, catalog, provider, out, err)
    except asyncio.CancelledError:
        if not received:
            raise
        task.uncancel()
        return 128 + received[0]
    finally:
        for number in (signal.SIGINT, *CLOSING):
            loop.remove_signal_handler(number)


async def _print(
    sessions: Sessions,
    prompt: str,
    read_all: ReadAll | None,
    catalog: ModelCatalog,
    provider: str,
    out: TextIO,
    err: TextIO,
) -> int:
    try:
        piped = None if read_all is None else await read_all(MAX_INPUT)
    except InputTooLarge as exc:
        print(f"error: {exc}", file=err, flush=True)
        return EXIT_ERROR
    text = instruction(prompt, piped)
    if not text.strip():
        print(
            'error: -p needs an instruction: maha -p "…", or pipe it to maha -p',
            file=err,
            flush=True,
        )
        return EXIT_USAGE
    conversation = await sessions.start()
    try:
        note = model_note(catalog, provider, conversation.model)
        if note is not None:
            print(f"  {note}", file=err, flush=True)
        result = await run_once(
            conversation, text, lambda event: _show(event, conversation, err)
        )
    except asyncio.CancelledError:
        print("  [interrupted]", file=err, flush=True)
        raise
    except Exception as exc:
        # A bug, or the disk failing: the turn kept what ran.
        detail = clean(f"{type(exc).__name__}: {exc}")
        print(f"error: internal: {detail}", file=err, flush=True)
        return EXIT_ERROR
    finally:
        await conversation.close()
        warn_unsaved(conversation, err)
        warn_trace(conversation, err)
    _answer(result.text, out)
    if result.error is not None:
        print(f"error: {clean(result.error)}", file=err, flush=True)
    return exit_code(result)


def exit_code(result: RunResult) -> int:
    """0 if the turn ended well, 1 if the model failed."""
    return EXIT_ERROR if result.reason == "error" else EXIT_OK


def _show(event: AgentEvent, conversation: Conversation, err: TextIO) -> None:
    """What the conversation shows of a turn but its text, on stderr."""
    match event:
        case ToolCallProposed(call=call):
            print(f"  → {call_line(call)}", file=err, flush=True)
        case ToolFinished():
            mark = "✗" if event.result.is_error else "✓"
            print(f"  {mark} {clean(event.summary)}", file=err, flush=True)
            warn_crash(event, err)
        case TurnFinished():
            note = turn_note(event)
            if event.reason == "denied":
                # Nobody can be asked: what is not allowed is denied.
                note = "[denied: --allow TOOL lets a tool run in this directory]"
            for line in (note, usage_line(event, conversation)):
                if line is not None:
                    print(f"  {line}", file=err)
            err.flush()


def _answer(text: str, out: TextIO) -> None:
    """The final answer, ending in a newline. To a terminal, clean, as in
    the conversation; to a file or a pipe, as the model wrote it: it is
    data for a program, as with `cat`."""
    if not text:
        return
    shown = clean(text) if out.isatty() else text
    out.write(shown if shown.endswith("\n") else shown + "\n")
    out.flush()
