"""The conversation in the terminal: read, send, show (spec hito 2, §1.11).

The answer is shown as it arrives (spec hito 3, §1.10), with every tool
call the agent makes (spec hito 4, §1.9).
"""

import asyncio
import json
import logging
import signal
import sys
from contextlib import aclosing
from pathlib import Path
from typing import TextIO

from mharness import __version__
from mharness.adapters.cli.commands import Commands, parse_command
from mharness.adapters.cli.input import Discard, ReadLine, StdinLines
from mharness.adapters.cli.spinner import Spinner, use_color
from mharness.adapters.cli.text import clean, clean_line, usd
from mharness.application.sessions import Conversation, Resumed, Sessions, Start
from mharness.domain.agent_events import (
    ApprovalRequested,
    ModelFallback,
    ModelRetry,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
)
from mharness.domain.errors import ModelError
from mharness.domain.events import TextDelta
from mharness.domain.messages import ToolCallBlock
from mharness.domain.model import Usage
from mharness.domain.session import SessionError
from mharness.ports.catalog import ModelCatalog

# Bugs of ours, for whoever maintains maha (spec hito 7, §1.11).
_log = logging.getLogger(__name__)

# Terminal convention for a program stopped by Ctrl+C: 128 + SIGINT.
EXIT_INTERRUPTED = 130
# A tool call is shown in one line, cut to this length.
MAX_CALL = 100


# Closing the window (SIGHUP) or `kill` (SIGTERM) end maha the way Ctrl+C
# cancels: what runs is killed on the way out (spec
# mejora-2026-10-26-deuda-pre-hito-6, A4).
CLOSING = (signal.SIGHUP, signal.SIGTERM)


class _Sigint:
    """Whether Ctrl+C asked to cancel the task, and that request was not
    handled yet; or the closing signal that asked to end. Tells them apart
    from any other cancellation."""

    def __init__(self) -> None:
        self.pending = False
        self.closing: int | None = None


async def converse(
    sessions: Sessions,
    *,
    provider: str,
    catalog: ModelCatalog,
    read_line: ReadLine | None = None,
    discard: Discard | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
    home: Path | None = None,
    start: Start | None = None,
) -> int:
    """Run the conversation until /exit, Ctrl+D or Ctrl+C; return the exit code.

    A new session, or the one `start` resumes (spec hito 8, §1.12), saved
    turn by turn; the commands of maha can resume another (spec hito 6,
    §1.8). `discard` drops what was typed ahead of a question.
    """
    read = read_line or StdinLines().readline
    # Looked up now, not at import time, in case they were replaced.
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    try:
        opened = await sessions.open(start)
    except SessionError as exc:
        print(f"error: {clean(str(exc))}", file=err, flush=True)
        return 1
    commands = Commands(
        sessions,
        opened.conversation,
        catalog=catalog,
        provider=provider,
        read=read,
        discard=discard,
        out=out,
        err=err,
        home=Path.home() if home is None else home,
    )
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    assert task is not None
    sigint = _Sigint()

    def on_sigint() -> None:
        sigint.pending = True
        task.cancel()

    def on_closing(number: int) -> None:
        sigint.closing = number
        task.cancel()

    loop.add_signal_handler(signal.SIGINT, on_sigint)
    for number in CLOSING:
        loop.add_signal_handler(number, on_closing, number)
    try:
        return await _turns(commands, provider, read, out, err, sigint, opened.resumed)
    except asyncio.CancelledError:
        if sigint.closing is not None:
            task.uncancel()
            return 128 + sigint.closing
        # Ctrl+C at the prompt ends `maha`; an answer handles its own.
        if not sigint.pending:
            raise
        task.uncancel()
        print(file=out)
        return EXIT_INTERRUPTED
    finally:
        loop.remove_signal_handler(signal.SIGINT)
        for number in CLOSING:
            loop.remove_signal_handler(number)
        # What is still pending is saved, and the session let go.
        await commands.conversation.close()
        commands.warn_unsaved()


async def _turns(
    commands: Commands,
    provider: str,
    read: ReadLine,
    out: TextIO,
    err: TextIO,
    sigint: _Sigint,
    resumed: Resumed | None,
) -> int:
    model = commands.conversation.model
    print(
        f"maha {__version__} · {provider} · {model} · /help for commands",
        file=out,
    )
    if resumed is not None:
        commands.tell_resumed(resumed)
    else:
        commands.note_model()
    while True:
        print("> ", end="", file=out, flush=True)
        try:
            line = (await read()).strip()
        except EOFError:
            print(file=out)
            return 0
        if not line:
            continue
        command = parse_command(line)
        if command is None:
            await _answer(commands.conversation, line, out, err, sigint)
            commands.warn_unsaved()
            commands.warn_trace()
        elif command.name == "exit":
            return 0
        else:
            await commands.run(command)


async def _answer(
    conversation: Conversation, line: str, out: TextIO, err: TextIO, sigint: _Sigint
) -> None:
    """Show one answer as it arrives.

    A model error or Ctrl+C ends only this answer (spec hito 3, §1.10). The
    agent keeps what already ran, and nothing else (spec hito 5, §1.5).
    """
    # True while the cursor is after text, not at the start of a line.
    wrote = False
    # True while a question waits after "Allow? …:" (spec
    # mejora-2026-10-26-deuda-pre-hito-6, B8).
    asking = False
    # Covers each wait for the model (spec hito 3, §1.12).
    spinner = Spinner(out, color=use_color())
    spinner.start()
    try:
        async with aclosing(conversation.run(line)) as events:
            async for event in events:
                match event:
                    case TextDelta(text=text):
                        await spinner.stop()
                        out.write(clean(text))
                        out.flush()
                        wrote = True
                    case ToolCallProposed(call=call):
                        await spinner.stop()
                        if wrote:
                            print(file=out)
                            wrote = False
                        print(f"  → {call_line(call)}", file=out, flush=True)
                    case ApprovalRequested():
                        asking = True
                    case ModelRetry() | ModelFallback():
                        await spinner.stop()
                        if wrote:
                            print(file=out)
                            wrote = False
                        print(f"  {retry_note(event)}", file=out, flush=True)
                        # The model is called again.
                        spinner.start()
                    case ToolFinished():
                        asking = False
                        mark = "✗" if event.result.is_error else "✓"
                        print(f"  {mark} {clean(event.summary)}", file=out, flush=True)
                        warn_crash(event, err)
                        # The model is called again.
                        spinner.start()
                    case TurnFinished():
                        await spinner.stop()
                        if wrote:
                            print(file=out)
                            wrote = False
                        note = turn_note(event)
                        if event.reason == "denied":
                            # The model is not called again: the person
                            # writes next (spec hito 5, §1.4).
                            note = "[denied: tell maha how to continue]"
                        if note is not None:
                            print(f"  {note}", file=out)
                        tokens = usage_line(event, conversation)
                        if tokens is not None:
                            print(f"  {tokens}", file=out)
                        out.flush()
    except ModelError as exc:
        await spinner.stop()
        # The text already shown stays; the error starts on a new line.
        if wrote:
            print(file=out)
        print(f"error: {clean(str(exc))}", file=err, flush=True)
    except Exception as exc:
        # A bug, or the terminal failing: the agent already kept what ran,
        # and maha goes on (spec mejora-2026-10-26-deuda-pre-hito-6, B1).
        await spinner.stop()
        if wrote:
            print(file=out)
        detail = clean(f"{type(exc).__name__}: {exc}")
        print(f"error: internal: {detail}", file=err, flush=True)
    except asyncio.CancelledError:
        # A closing signal goes on up: maha ends, not just the answer.
        if not sigint.pending or sigint.closing is not None:
            raise
        sigint.pending = False
        # Without this, asyncio would keep treating the task as cancelled.
        task = asyncio.current_task()
        assert task is not None
        task.uncancel()
        await spinner.stop()
        if wrote or asking:
            print(file=out)
        print("  [interrupted]", file=out, flush=True)
    finally:
        await spinner.stop()


def call_line(call: ToolCallBlock) -> str:
    """`name(arg="value", …)` in one line, at most 100 characters."""
    try:
        arguments = json.loads(call.arguments or "{}")
    except ValueError, RecursionError:
        arguments = None
    if isinstance(arguments, dict):
        shown = ", ".join(
            f"{key}={json.dumps(value, ensure_ascii=False)}"
            for key, value in arguments.items()
        )
    else:
        # As the model wrote it: the loop answers it with an error.
        shown = call.arguments
    text = clean(" ".join(f"{call.name}({shown})".split()))
    return text if len(text) <= MAX_CALL else text[: MAX_CALL - 1] + "…"


def retry_note(event: ModelRetry | ModelFallback) -> str:
    """What the person should know of a retry or a fallback (spec hito 8,
    §1.14): the fallback always, so that it does not hide a failing model."""
    model = clean_line(event.model)
    error = clean_line(event.error)
    if isinstance(event, ModelRetry):
        wait = f"{round(event.delay, 1):g} s"
        return (
            f"[{model}: {error}; retrying in {wait} "
            f"({event.attempt}/{event.max_retries})]"
        )
    return f"[{model} keeps failing ({error}); {clean_line(event.fallback)} goes on]"


def warn_crash(event: ToolFinished, err: TextIO) -> None:
    """A tool that crashed is a bug of ours: said, and logged."""
    if not event.internal_error:
        return
    # Only its kind: the message may carry what the tool read, and the log
    # never holds content.
    _log.warning(
        "tool %s failed: %s", event.call.name, event.internal_error.split(":", 1)[0]
    )
    print(
        f'warning: tool "{clean(event.call.name)}" failed: '
        f"{clean(event.internal_error)}",
        file=err,
        flush=True,
    )


def turn_note(turn: TurnFinished) -> str | None:
    """Which limit stopped the turn, if one did. A denial is told by each
    caller: what to do next is not the same with and without a person."""
    if turn.reason == "max_steps":
        return f"[step limit reached: {turn.steps}]"
    if turn.reason == "max_tokens":
        tokens = turn.usage.input_tokens + turn.usage.output_tokens
        return f"[token limit reached: {tokens} tokens]"
    if turn.reason == "timeout":
        return "[time limit reached]"
    if turn.reason == "max_cost":
        if turn.cost is None:
            return "[cost limit: the cost of a call is not known]"
        return f"[cost limit reached: {usd(turn.cost)}]"
    return None


def usage_line(turn: TurnFinished, conversation: Conversation) -> str | None:
    """`[tokens: … · calls · cost · session cost]`; None if nothing is known."""
    usage = turn.usage
    # All zeros and no cost: the provider reported nothing, or no call
    # ended (a time limit while the model answered).
    if usage == Usage() and not turn.cost:
        return None
    parts = [f"tokens: {usage.input_tokens} in · {usage.output_tokens} out"]
    if usage.reasoning_tokens:
        # Already inside "out": what the model thought, billed as output.
        parts[0] += f" ({usage.reasoning_tokens} reasoning)"
    if turn.tool_calls:
        parts.append(f"{turn.tool_calls} call" + ("s" if turn.tool_calls > 1 else ""))
    if turn.cost is not None:
        parts.append(usd(turn.cost))
    # The turns without a price are not in the sum: it is at least that.
    if conversation.cost or (turn.cost is not None and not conversation.uncosted_turns):
        at_least = "≥" if conversation.uncosted_turns else ""
        parts.append(f"session {at_least}{usd(conversation.cost)}")
    return f"[{' · '.join(parts)}]"
