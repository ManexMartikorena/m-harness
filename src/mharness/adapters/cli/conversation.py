"""The conversation in the terminal: read, send, show (spec hito 2, §1.11).

The answer is shown as it arrives (spec hito 3, §1.10), with every tool
call the agent makes (spec hito 4, §1.9).
"""

import asyncio
import json
import logging
import signal
import sys
from collections.abc import Callable, Sequence
from contextlib import aclosing
from pathlib import Path
from typing import TextIO

from mharness import __version__
from mharness.adapters.cli.approval import show_covered
from mharness.adapters.cli.commands import Commands, parse_command
from mharness.adapters.cli.init import TAKES_EFFECT, Init
from mharness.adapters.cli.input import Discard, ReadLine, StdinLines
from mharness.adapters.cli.spinner import Spinner, use_color
from mharness.adapters.cli.text import clean, clean_line, usd
from mharness.adapters.cli.todo import finished_todo, is_todo
from mharness.application.sessions import Conversation, Resumed, Sessions, Start
from mharness.domain.agent_events import (
    ApprovalCovered,
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
from mharness.domain.question import ASK_TOOL, questions_of
from mharness.domain.session import SessionError
from mharness.ports.catalog import ModelCatalog

# Bugs of ours, for whoever maintains maha (spec hito 7, §1.11).
_log = logging.getLogger(__name__)

# Terminal convention for a program stopped by Ctrl+C: 128 + SIGINT.
EXIT_INTERRUPTED = 130
AGAIN_TO_QUIT = "[Ctrl+C again to quit, or /exit]"
INTERRUPTED = "[interrupted]"
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
    notes: Sequence[str] = (),
    init: Init | None = None,
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
        if sigint.pending:
            # Not taken yet: a second press would cut what handles the
            # first, as the save while leaving (review of the audit).
            return
        sigint.pending = True
        task.cancel()

    def on_closing(number: int) -> None:
        sigint.closing = number
        task.cancel()

    loop.add_signal_handler(signal.SIGINT, on_sigint)
    for number in CLOSING:
        loop.add_signal_handler(number, on_closing, number)
    try:
        code = await _turns(
            commands, provider, read, out, err, sigint, opened.resumed, notes, init
        )
    except asyncio.CancelledError:
        if sigint.closing is not None:
            task.uncancel()
            code = 128 + sigint.closing
        else:
            # Ctrl+C before the prompt ends `maha`; the prompt, an answer
            # and a command handle their own.
            if not sigint.pending:
                raise
            task.uncancel()
            print(file=out)
            code = EXIT_INTERRUPTED
    finally:
        # What is still pending is saved, and the session let go. Ctrl+C
        # while its title comes skips the title: our handler is still
        # there, and the rest is saved and told (review of the audit after
        # hito 10). A closing signal does not wait for the title, nor
        # writes to a terminal that may be gone (second review).
        closing = sigint.closing is not None
        try:
            if not closing:
                commands.tell_naming()
            await commands.conversation.close(title=not closing)
        except asyncio.CancelledError:
            if sigint.closing is None and not _ours(sigint):
                raise
            if sigint.closing is not None:
                task.uncancel()
        finally:
            loop.remove_signal_handler(signal.SIGINT)
            for number in CLOSING:
                loop.remove_signal_handler(number)
        _tell_if_heard(commands.warn_unsaved, closed=sigint.closing is not None)
    # A closing signal while leaving says so too (review of the audit after
    # hito 10).
    return code if sigint.closing is None else 128 + sigint.closing


def _tell_if_heard(tell: Callable[[], None], *, closed: bool) -> None:
    """Tell the person something on the way out; after a closing signal the
    terminal may be gone (a closed window), and its error ends nothing."""
    try:
        tell()
    except OSError:
        if not closed:
            raise


async def _turns(
    commands: Commands,
    provider: str,
    read: ReadLine,
    out: TextIO,
    err: TextIO,
    sigint: _Sigint,
    resumed: Resumed | None,
    notes: Sequence[str],
    init: Init | None = None,
) -> int:
    # From the configuration or a resumed session: escaped as any other
    # text that may come from a file (deep audit after hito 9, I3).
    model = clean_line(commands.conversation.model)
    print(
        f"maha {__version__} · {clean_line(provider)} · {model} · /help for commands",
        file=out,
    )
    if resumed is not None:
        commands.tell_resumed(resumed)
    else:
        commands.note_model()
        commands.note_prompt()
    for note in notes:
        print(f"  {note}", file=out, flush=True)
    # Ctrl+C at the prompt clears the line and says how to leave; a second
    # one in a row leaves (audit after hito 10, P1).
    armed = False
    while True:
        print("> ", end="", file=out, flush=True)
        try:
            line = (await read()).strip()
        except EOFError:
            print(file=out)
            return 0
        except asyncio.CancelledError:
            if not _ours(sigint):
                raise
            print(file=out)
            if armed:
                return EXIT_INTERRUPTED
            armed = True
            print(f"  {AGAIN_TO_QUIT}", file=out, flush=True)
            continue
        armed = False
        if not line:
            continue
        command = parse_command(line)
        if command is None:
            await _answer(commands.conversation, line, out, err, sigint)
            commands.warn_unsaved()
            commands.warn_trace()
        elif command.name == "exit":
            return 0
        elif command.name == "init" and init is not None:
            if init.note is not None:
                print(f"  {init.note}", file=out, flush=True)
            before = init.stamp()
            text = init.text(command.argument)
            await _answer(commands.conversation, text, out, err, sigint)
            commands.warn_unsaved()
            commands.warn_trace()
            if init.stamp() not in (None, before):
                # Written or changed: the prompt of this session is fixed.
                print(f"  {TAKES_EFFECT}", file=out, flush=True)
        else:
            try:
                await commands.run(command)
            except asyncio.CancelledError:
                # It ends the command, not maha (audit after hito 10, I8).
                if not _ours(sigint):
                    raise
                print(f"\n  {INTERRUPTED}", file=out, flush=True)


def _ours(sigint: _Sigint) -> bool:
    """Whether the cancellation is a Ctrl+C to handle here: then it is
    taken, and the task goes on. A closing signal, or any other
    cancellation, goes on up."""
    if not sigint.pending or sigint.closing is not None:
        return False
    sigint.pending = False
    task = asyncio.current_task()
    assert task is not None
    task.uncancel()
    return True


async def _answer(
    conversation: Conversation, line: str, out: TextIO, err: TextIO, sigint: _Sigint
) -> None:
    """Show one answer as it arrives.

    A model error or Ctrl+C ends only this answer (spec hito 3, §1.10). The
    agent keeps what already ran, and nothing else (spec hito 5, §1.5).
    """
    # True while the cursor is after text, not at the start of a line.
    wrote = False
    # The block of that text: another one starts on a new line, as the
    # session keeps it (review of the deep audit).
    block: int | None = None
    # True while a question waits after "Allow? …:" (spec
    # mejora-2026-10-26-deuda-pre-hito-6, B8).
    asking = False
    # A "\r" that ended the last piece: with a "\n" next it ends a line,
    # and is not shown as \x0d (review of the audit after hito 10, I10).
    held = ""
    # Covers each wait for the model (spec hito 3, §1.12).
    spinner = Spinner(out, color=use_color())
    spinner.start()
    try:
        async with aclosing(conversation.run(line)) as events:
            async for event in events:
                if held and (not isinstance(event, TextDelta) or event.block != block):
                    # It did not end a line: shown as what it is.
                    out.write(clean(held))
                    held = ""
                match event:
                    case TextDelta(text=text):
                        await spinner.stop()
                        other = event.block is not None and block is not None
                        if wrote and other and event.block != block:
                            out.write("\n")
                        block = event.block
                        text = held + text
                        held = "\r" if text.endswith("\r") else ""
                        out.write(clean(text.removesuffix(held)))
                        out.flush()
                        wrote = True
                    case ToolCallProposed(call=call):
                        await spinner.stop()
                        if wrote:
                            print(file=out)
                            wrote = False
                        if call.name == ASK_TOOL:
                            # Its questions are shown instead; Ctrl+C there
                            # ends on a new line, as at an approval.
                            asking = True
                        elif not is_todo(call.name):
                            print(f"  → {call_line(call)}", file=out, flush=True)
                    case ApprovalRequested():
                        asking = True
                    case ApprovalCovered(request=request):
                        show_covered(request, out)
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
                        # Styles only on a terminal: never in a pipe or a file.
                        styled = use_color() and out.isatty()
                        show_finished(event, out, color=styled)
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
        if not _ours(sigint):
            raise
        await spinner.stop()
        if wrote or asking:
            print(file=out)
        print(f"  {INTERRUPTED}", file=out, flush=True)
    finally:
        await spinner.stop()


def show_finished(event: ToolFinished, out: TextIO, *, color: bool = False) -> None:
    """`✓ 3 lines` after a call; the list after a call to `todo_write`,
    whose call line was not shown (spec hito 10, §1.10), as it is not for
    `ask_user`: its questions were (§1.11)."""
    todo = finished_todo(event, color=color)
    if todo is not None:
        print("\n".join(todo), file=out, flush=True)
        return
    unseen = event.call.name == ASK_TOOL and questions_of(event.call.arguments) is None
    if is_todo(event.call.name) or unseen:
        # Its call line was not shown: a call whose list or questions could
        # not be drawn is shown as any other, with its error.
        print(f"  → {call_line(event.call)}", file=out)
    mark = "✗" if event.result.is_error else "✓"
    print(f"  {mark} {clean(event.summary)}", file=out, flush=True)


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


def title_failed(kind: str) -> None:
    """A title the small model could not write: only to maha.log, by its
    kind; the session keeps its first line (spec hito 10, §1.12)."""
    _log.warning("session title not written: %s", kind)


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
    if turn.reason == "max_output":
        return "[the answer was cut: the model reached its output limit]"
    if turn.reason == "refused":
        return "[the model declined to answer]"
    if turn.reason == "context_full":
        return (
            "[the conversation filled the model's context window: /new starts another]"
        )
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
