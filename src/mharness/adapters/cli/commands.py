"""What a line is: a command for maha, or text for the model (spec hito 6,
§1.8)."""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TextIO

from mharness.adapters.cli.export import markdown
from mharness.adapters.cli.input import Discard, ReadLine
from mharness.adapters.cli.spinner import use_color
from mharness.adapters.cli.text import clean, clean_line, usd
from mharness.application.sessions import (
    Conversation,
    Resumed,
    Sessions,
    TraceReport,
)
from mharness.application.traces import TraceSummary, TurnSummary
from mharness.domain.session import SessionError, SessionNotFound
from mharness.domain.trace import TraceError
from mharness.ports.catalog import ModelCatalog

# What each command does, for /help.
COMMANDS = {
    "sessions": "/sessions — the recent sessions, of every directory",
    "resume": "/resume [ID] — resume a session; without ID, the last one here",
    "delete": "/delete ID — delete a session",
    "model": "/model [ID] — show the model, or change it",
    "trace": "/trace [ID] — what a session did and cost; without ID, this one",
    "new": "/new — a new session, with the same model",
    "export": "/export [FILE] — this conversation in Markdown; by default, ID.md",
    "help": "/help — this list",
    "exit": "/exit — quit",
}
# What the catalog says of a model (spec hito 7, §1.10).
NOT_IN_CATALOG = "[model not in the catalog: cost only if the provider reports it]"
TRAINS_ON_DATA = "[warning: this model may use your data for training]"
# /sessions shows the most recent ones.
SESSIONS_SHOWN = 20
# "/" and lowercase letters, as the first word: "/etc/hosts …" is text.
_NAME = re.compile(r"/([a-z]+)")


@dataclass(frozen=True)
class Command:
    name: str
    argument: str | None


def parse_command(line: str) -> Command | None:
    """The command in `line`, known or not; None if it goes to the model."""
    first, _, rest = line.partition(" ")
    match = _NAME.fullmatch(first)
    if match is None:
        return None
    return Command(match.group(1), rest.strip() or None)


class Commands:
    """Runs the commands of maha over the sessions; `conversation` is the
    current one, which /resume replaces."""

    def __init__(
        self,
        sessions: Sessions,
        conversation: Conversation,
        *,
        catalog: ModelCatalog,
        provider: str,
        read: ReadLine,
        discard: Discard | None,
        out: TextIO,
        err: TextIO,
        home: Path,
    ) -> None:
        self._sessions = sessions
        self.conversation = conversation
        self._catalog = catalog
        self._provider = provider
        self._read = read
        self._discard = discard
        self._out = out
        self._err = err
        self._home = home

    async def run(self, command: Command) -> None:
        """Run any command but /exit, which the conversation handles."""
        try:
            match command.name:
                case "help":
                    for line in COMMANDS.values():
                        self._say(line)
                case "sessions":
                    await self._list()
                case "resume":
                    await self._resume(command.argument)
                case "delete":
                    await self._delete(command.argument)
                case "trace":
                    await self._trace(command.argument)
                case "model":
                    await self._model(command.argument)
                case "export":
                    await self._export(command.argument)
                case "new":
                    await self._new()
                case _:
                    self._say(f"unknown command: /{command.name} (see /help)")
        except (SessionError, TraceError) as exc:
            print(f"error: {clean(str(exc))}", file=self._err, flush=True)
        except Exception as exc:
            # A bug, or the disk failing in a way nobody expected: said, and
            # maha goes on, as with an answer (final audit of hito 6).
            detail = clean(f"{type(exc).__name__}: {exc}")
            print(f"error: internal: {detail}", file=self._err, flush=True)
        self.warn_unsaved()

    def note_model(self) -> None:
        """What the catalog says of the model in use (spec hito 7, §1.10)."""
        note = model_note(self._catalog, self._provider, self.conversation.model)
        if note is None:
            return
        if note == TRAINS_ON_DATA and use_color() and self._out.isatty():
            note = f"\x1b[33m{note}\x1b[0m"
        self._say(note)

    def warn_trace(self) -> None:
        warn_trace(self.conversation, self._err)

    def warn_unsaved(self) -> None:
        warn_unsaved(self.conversation, self._err)

    async def _list(self) -> None:
        for line in await session_lines(self._sessions, self._home):
            print(f"  {line}", file=self._out)
        self._out.flush()

    async def _resume(self, session: str | None) -> None:
        left = self.conversation.id if self.conversation.stored else None
        try:
            resumed = await self._sessions.resume(session, current=self.conversation)
        except SessionNotFound as exc:
            if session is None:
                raise SessionNotFound(f"{exc} (see /sessions)") from None
            raise
        self.conversation = resumed.conversation
        self._warn_lost(left, resumed.left_unsaved)
        self.tell_resumed(resumed)

    def tell_resumed(self, resumed: Resumed) -> None:
        """What the person should know of the session just resumed."""
        for note in resumed_notes(resumed, self._sessions.cwd, self._home):
            self._say(note)
        self.note_model()

    async def _delete(self, session: str | None) -> None:
        if session is None:
            self._say("usage: /delete ID")
            return
        if self.conversation.exists and session == self.conversation.id:
            # Before asking: it would be refused anyway.
            raise SessionError("this is the current session")
        # A question too: a "y" pasted after the command must not answer it
        # (spec mejora-2026-10-26-deuda-pre-hito-6, A2).
        if self._discard is not None and self._discard():
            self._say("(discarded typed input)")
        print(
            f"  Delete session {clean_line(session)}? [y/N]: ",
            end="",
            file=self._out,
            flush=True,
        )
        try:
            answer = (await self._read()).strip().casefold()
        except EOFError:
            print(file=self._out)
            answer = ""
        if answer not in ("y", "yes", "s", "sí", "si"):
            self._say("[not deleted]")
            return
        await self._sessions.delete(session, current=self.conversation)
        self._say(f"[deleted {clean_line(session)}]")

    async def _model(self, model: str | None) -> None:
        if model is not None:
            await self.conversation.switch_model(model)
        self._say(f"[model: {clean_line(self.conversation.model)}]")
        if model is not None:
            self.note_model()

    async def _trace(self, session: str | None) -> None:
        """A row per turn and the total; the detail, in the file (spec hito
        7, §1.9). Everything that comes from the disk is escaped."""
        report = await self._sessions.trace(session, current=self.conversation)
        for line in trace_lines(report, self._home):
            self._say(line)

    async def _new(self) -> None:
        """A new session without leaving maha (spec hito 8, §1.15). The
        model chosen with /model stays: it is this maha's choice."""
        old = self.conversation
        left = old.id if old.stored else None
        fresh = await self._sessions.start(old.model)
        # The new one is ready: only now is the current one let go.
        await old.close()
        self.conversation = fresh
        self._warn_lost(left, old.unsaved)
        self._say("[new session]")

    def _warn_lost(self, left: str | None, unsaved: str | None) -> None:
        """The session left behind could not save its last turns."""
        if unsaved is None:
            return
        # Without id: its session could not even be created.
        what = f"session {clean_line(left)}" if left else "the conversation"
        print(
            f"warning: {what} was not saved, its last turns are lost: {clean(unsaved)}",
            file=self._err,
            flush=True,
        )

    async def _export(self, file: str | None) -> None:
        """This conversation in Markdown, to `file` or to `ID.md`, next to
        maha; never over a file that exists (spec hito 8, §1.15)."""
        conversation = self.conversation
        if not conversation.stored:
            self._say("(nothing to export yet)")
            return
        text = markdown(await self._sessions.read(conversation.id))
        name = file or f"{conversation.id}.md"
        path = await asyncio.to_thread(_write_new, Path(self._sessions.cwd), name, text)
        self._say(f"[exported to {self._shown(str(path))}]")

    def _shown(self, cwd: str) -> str:
        return shown_dir(cwd, self._home)

    def _say(self, text: str) -> None:
        print(f"  {text}", file=self._out, flush=True)


async def session_lines(sessions: Sessions, home: Path) -> list[str]:
    """The recent sessions of every directory, one per line, those of this
    one marked with `*`; or `(no sessions)`."""
    found = (await sessions.summaries())[:SESSIONS_SHOWN]
    if not found:
        return ["(no sessions)"]
    lines = []
    for summary in found:
        mark = "*" if sessions.here(summary) else " "
        when = f"{summary.updated_at.astimezone():%Y-%m-%d %H:%M}"
        count = f"{summary.messages} message" + ("" if summary.messages == 1 else "s")
        lines.append(
            f"{mark} {clean_line(summary.id)}  {when}  {count}  "
            f"{shown_dir(summary.cwd, home)}  {clean_line(summary.title)}"
        )
    return lines


def _write_new(cwd: Path, name: str, text: str) -> Path:
    """Write `text` to `name`, from `cwd`, creating its folder; never over
    a file that exists. Raises `SessionError`."""
    path = cwd / Path(name).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as target:
            target.write(text)
    except FileExistsError:
        raise SessionError(f"{path} already exists") from None
    except OSError as exc:
        raise SessionError(f"cannot write {path}: {exc.strerror}") from None
    return path


def resumed_notes(resumed: Resumed, cwd: str, home: Path) -> list[str]:
    """`[resumed …]`, and where the session was and which model it had if
    that is not what is used now. `cwd` is where the tools work."""
    conversation = resumed.conversation
    notes = [
        f"[resumed {clean_line(conversation.id)} · "
        f"{resumed.messages} messages · {clean_line(conversation.model)}]"
    ]
    if resumed.other_cwd is not None:
        notes.append(
            f"[this session was in {shown_dir(resumed.other_cwd, home)}; "
            f"tools work in {shown_dir(cwd, home)}]"
        )
    if resumed.fallback_from is not None:
        notes.append(
            f"[model {clean_line(resumed.fallback_from)} is of another provider; "
            f"using {clean_line(conversation.model)}]"
        )
    if resumed.interrupted:
        notes.append("[the last answer was interrupted]")
    return notes


def shown_dir(cwd: str, home: Path) -> str:
    """A directory, with `~` for the home, clean."""
    path = PurePath(cwd)
    if path.is_relative_to(home):
        relative = path.relative_to(home)
        return clean_line("~" if relative == PurePath() else f"~/{relative}")
    return clean_line(cwd)


def model_note(catalog: ModelCatalog, provider: str, model: str) -> str | None:
    """What the catalog says of `model`: not in it, or it may train on the
    data (ANALISIS §9). The model is used anyway: a new one may not be in
    the catalog yet."""
    info = catalog.get(provider, model)
    if info is None:
        return NOT_IN_CATALOG
    return TRAINS_ON_DATA if info.trains_on_data else None


def warn_trace(conversation: Conversation, err: TextIO) -> None:
    """A trace that fails does not stop maha: it is said, once (spec hito
    7, §1.7)."""
    reason = conversation.trace_warning()
    if reason is not None:
        print(f"warning: trace not saved: {clean(reason)}", file=err, flush=True)


def warn_unsaved(conversation: Conversation, err: TextIO) -> None:
    """A failed save does not stop maha: it is said (spec hito 6, §1.6)."""
    if conversation.unsaved is not None:
        reason = clean(conversation.unsaved)
        print(f"warning: session not saved: {reason}", file=err, flush=True)


def trace_lines(report: TraceReport, home: Path) -> list[str]:
    """A row per turn, the total and where the whole trace is."""
    summary = report.summary
    lines = _summary_lines(summary) if summary.turns else ["(no turns in the trace)"]
    return [*lines, f"[trace: {shown_dir(report.location, home)}]"]


def _summary_lines(summary: TraceSummary) -> list[str]:
    models = ", ".join(clean_line(model) for model in summary.models) or "no model"
    lines = [
        f"{clean_line(summary.session)} · {models} · "
        f"{_count(len(summary.turns), 'turn')} · "
        f"{_count(summary.model_calls, 'model call')} · "
        f"{_count(summary.tools, 'tool')}"
    ]
    lines += [_turn_line(turn) for turn in summary.turns]
    usage = summary.usage
    if summary.uncosted_turns == len(summary.turns):
        # No turn has a price: "≥$0" would be true and say nothing.
        cost = "cost unknown"
    else:
        cost = ("≥" if summary.uncosted_turns else "") + usd(summary.cost)
    lines.append(f"total: {usage.input_tokens} in · {usage.output_tokens} out · {cost}")
    return lines


def _turn_line(turn: TurnSummary) -> str:
    parts = [
        _count(turn.model_calls, "call"),
        _count(turn.tools, "tool"),
        f"{turn.usage.input_tokens} in",
        f"{turn.usage.output_tokens} out",
    ]
    if turn.cost is not None:
        parts.append(usd(turn.cost))
    parts.append(f"{turn.seconds:.1f} s")
    if turn.failed_tools:
        parts.append(f"{turn.failed_tools} failed")
    if turn.denied_tools:
        parts.append(f"{turn.denied_tools} denied")
    if turn.ended != "end_turn":
        parts.append(_ENDINGS[turn.ended])
    started = f"{turn.started_at.astimezone():%H:%M:%S}"
    return f"{turn.number}  {started}  {' · '.join(parts)}"


# How a turn that did not just answer ended.
_ENDINGS = {
    "max_steps": "step limit",
    "max_cost": "cost limit",
    "max_tokens": "token limit",
    "timeout": "time limit",
    "denied": "denied",
    "error": "error",
    "interrupted": "interrupted",
    "unfinished": "unfinished",
}


def _count(number: int, thing: str) -> str:
    return f"{number} {thing}" + ("" if number == 1 else "s")
