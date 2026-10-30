"""`maha -p`: one instruction without a person (spec hito 8, §1.10, §1.11
and §1.4).

```
$ git diff | maha -p "revisa este diff" > revision.md
  → read_file(path="src/app.py")          (stderr)
  ✓ 120 lines                             (stderr)
  [tokens: 5236 in · 410 out · 1 call]    (stderr)
```

In `text`, stdout gets only the final answer, so that `x=$(maha -p …)`
holds just that; the calls, the notes and the tokens go to stderr, as in
the conversation but without a spinner. In `json`, stdout gets one object
at the end, the result; in `stream-json`, one line per event and the
result last. JSON escapes every control character: it is safe in a
terminal as it is.
"""

import asyncio
import json
import os
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TextIO

from mharness.adapters.cli.commands import (
    model_note,
    resumed_notes,
    warn_trace,
    warn_unsaved,
)
from mharness.adapters.cli.conversation import (
    CLOSING,
    call_line,
    retry_note,
    turn_note,
    usage_line,
    warn_crash,
)
from mharness.adapters.cli.input import InputTooLarge, ReadAll
from mharness.adapters.cli.text import clean
from mharness.application.headless import RunResult, instruction, run_once
from mharness.application.sessions import Conversation, Sessions, Start
from mharness.domain.agent_events import (
    AgentEvent,
    ApprovalRequested,
    ModelFallback,
    ModelRetry,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
)
from mharness.domain.session import SessionError
from mharness.ports.catalog import ModelCatalog

# What may be piped to -p, at most: the same as Claude Code (spec §1.10).
MAX_INPUT = 10 * 1024 * 1024

type OutputFormat = Literal["text", "json", "stream-json"]

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
# A limit of the turn stopped it.
EXIT_LIMIT = 3
# A call was denied: the turn ended there.
EXIT_DENIED = 4


async def print_mode(
    sessions: Sessions,
    prompt: str,
    *,
    read_all: ReadAll | None,
    catalog: ModelCatalog,
    provider: str,
    output_format: OutputFormat = "text",
    start: Start | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
    home: Path | None = None,
) -> int:
    """Run `prompt`, with what `read_all` gives below it, in a new session
    or the one `start` resumes, and write the result in `output_format`;
    return the exit code. `read_all` is None when the input is a terminal.

    Ctrl+C and the closing signals end it as they end the conversation:
    what ran is saved, and the code is 128 + the signal.
    """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    shown = _Shown(output_format, err, Path.home() if home is None else home)
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
        return await _print(
            sessions, prompt, read_all, catalog, provider, start, out, shown
        )
    except asyncio.CancelledError:
        if not received:
            raise
        task.uncancel()
        return 128 + received[0]
    except BrokenPipeError:
        # Nobody reads stdout any more (`maha -p … | head -1`): what is left
        # is dropped, as is Python's last flush, which would print a trace.
        _drop(out)
        return EXIT_ERROR
    finally:
        for number in (signal.SIGINT, *CLOSING):
            loop.remove_signal_handler(number)


@dataclass(frozen=True)
class _Shown:
    """Where the notes go, and whether they go: only in `text`."""

    output_format: OutputFormat
    err: TextIO
    home: Path

    def note(self, text: str) -> None:
        if self.output_format == "text":
            print(f"  {text}", file=self.err, flush=True)


async def _print(
    sessions: Sessions,
    prompt: str,
    read_all: ReadAll | None,
    catalog: ModelCatalog,
    provider: str,
    start: Start | None,
    out: TextIO,
    shown: _Shown,
) -> int:
    err = shown.err
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
    try:
        opened = await sessions.open(start)
    except SessionError as exc:
        print(f"error: {clean(str(exc))}", file=err, flush=True)
        return EXIT_ERROR
    conversation = opened.conversation
    try:
        if opened.resumed is not None:
            for line in resumed_notes(opened.resumed, sessions.cwd, shown.home):
                shown.note(line)
        note = model_note(catalog, provider, conversation.model)
        if note is not None:
            shown.note(note)
        result = await run_once(
            conversation, text, _watch(shown.output_format, conversation, out, err)
        )
    except asyncio.CancelledError:
        print("  [interrupted]", file=err, flush=True)
        raise
    except BrokenPipeError:
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
    if shown.output_format == "text":
        _answer(result.text, out)
        if result.error is not None:
            print(f"error: {clean(result.error)}", file=err, flush=True)
    else:
        _json_line(result_object(result), out)
    return exit_code(result)


def exit_code(result: RunResult) -> int:
    """How the turn ended, for a script (spec hito 8, §1.4): 3 and 4 tell
    it whether to try again with a higher limit or with more permissions."""
    match result.reason:
        case "end_turn":
            return EXIT_OK
        case "error":
            return EXIT_ERROR
        case "denied":
            return EXIT_DENIED
        case "max_steps" | "max_cost" | "max_tokens" | "timeout":
            return EXIT_LIMIT


def result_object(result: RunResult) -> dict[str, Any]:
    """The result in JSON, with stable names (spec hito 8, §1.11).
    `is_error`: the turn did not end well, and the exit code is not 0."""
    data = result.model_dump(mode="json")
    return {
        "type": "result",
        "session_id": data["session"],
        "result": data["text"],
        "reason": data["reason"],
        "is_error": result.reason != "end_turn",
        "steps": data["steps"],
        "tool_calls": data["tool_calls"],
        "tool_errors": data["tool_errors"],
        "denials": data["denials"],
        "usage": data["usage"],
        "cost_usd": data["cost"],
        "duration_s": round(result.duration, 3),
        "model": data["model"],
        "error": data["error"],
    }


def _watch(
    output_format: OutputFormat, conversation: Conversation, out: TextIO, err: TextIO
) -> Callable[[AgentEvent], None]:
    """What is written of each event as it comes. A tool that crashed is
    told on stderr in every format: it is a bug of maha."""
    if output_format == "text":
        return _Progress(conversation, err).show

    def watch(event: AgentEvent) -> None:
        if output_format == "stream-json":
            _json_line(event.model_dump(mode="json"), out)
        if isinstance(event, ToolFinished):
            warn_crash(event, err)

    return watch


def _json_line(data: dict[str, Any], out: TextIO) -> None:
    out.write(json.dumps(data) + "\n")
    out.flush()


# Why a call was denied, said once the turn ends.
_NOT_ALLOWED = "[denied: --allow TOOL lets a tool run in this directory]"
_NEEDS_A_PERSON = (
    "[denied: never without a person: outside this directory, a secret or a "
    "file that runs code]"
)


class _Progress:
    """In `text`, what the conversation shows of a turn but its text, on
    stderr. A denial says what would let the call run: `--allow`, or
    nothing, when the request has no scope (spec hito 8, §1.2)."""

    def __init__(self, conversation: Conversation, err: TextIO) -> None:
        self._conversation = conversation
        self._err = err
        # The calls asked without a scope.
        self._scopeless: set[str] = set()
        self._why = _NOT_ALLOWED

    def show(self, event: AgentEvent) -> None:
        err = self._err
        match event:
            case ToolCallProposed(call=call):
                print(f"  → {call_line(call)}", file=err, flush=True)
            case ApprovalRequested(call=call, request=request):
                if request.scope is None:
                    self._scopeless.add(call.id)
            case ModelRetry() | ModelFallback():
                print(f"  {retry_note(event)}", file=err, flush=True)
            case ToolFinished():
                mark = "✗" if event.result.is_error else "✓"
                print(f"  {mark} {clean(event.summary)}", file=err, flush=True)
                warn_crash(event, err)
                if event.decision == "deny" and event.call.id in self._scopeless:
                    self._why = _NEEDS_A_PERSON
            case TurnFinished():
                note = self._why if event.reason == "denied" else turn_note(event)
                for line in (note, usage_line(event, self._conversation)):
                    if line is not None:
                        print(f"  {line}", file=err)
                err.flush()


def _drop(out: TextIO) -> None:
    """Point `out` at /dev/null, if it has a descriptor."""
    try:
        fd = out.fileno()
        devnull = os.open(os.devnull, os.O_WRONLY)
    except OSError, ValueError:
        return
    os.dup2(devnull, fd)
    os.close(devnull)


def _answer(text: str, out: TextIO) -> None:
    """The final answer, ending in a newline. To a terminal, clean, as in
    the conversation; to a file or a pipe, as the model wrote it: it is
    data for a program, as with `cat`."""
    if not text:
        return
    shown = clean(text) if out.isatty() else text
    out.write(shown if shown.endswith("\n") else shown + "\n")
    out.flush()
