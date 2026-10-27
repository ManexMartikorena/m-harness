"""What a line is: a command for maha, or text for the model (spec hito 6,
§1.8)."""

import re
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TextIO

from mharness.adapters.cli.input import Discard, ReadLine
from mharness.adapters.cli.spinner import use_color
from mharness.adapters.cli.text import clean, clean_line, usd
from mharness.application.sessions import Conversation, Sessions
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
    "help": "/help — this list",
    "exit": "/exit — quit",
}
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
        """What the catalog says of the model in use (spec hito 7, §1.10):
        not in it, or it may train on the data (ANALISIS §9). The model is
        used anyway: a new one may not be in the catalog yet."""
        info = self._catalog.get(self._provider, self.conversation.model)
        if info is None:
            self._say(
                "[model not in the catalog: cost only if the provider reports it]"
            )
        elif info.trains_on_data:
            warning = "[warning: this model may use your data for training]"
            if use_color() and self._out.isatty():
                warning = f"\x1b[33m{warning}\x1b[0m"
            self._say(warning)

    def warn_trace(self) -> None:
        """A trace that fails does not stop maha: it is said, once (spec
        hito 7, §1.7)."""
        reason = self.conversation.trace_warning()
        if reason is not None:
            print(
                f"warning: trace not saved: {clean(reason)}", file=self._err, flush=True
            )

    def warn_unsaved(self) -> None:
        """A failed save does not stop maha: it is said (spec hito 6, §1.6)."""
        if self.conversation.unsaved is not None:
            reason = clean(self.conversation.unsaved)
            print(f"warning: session not saved: {reason}", file=self._err, flush=True)

    async def _list(self) -> None:
        found = (await self._sessions.summaries())[:SESSIONS_SHOWN]
        if not found:
            self._say("(no sessions)")
        for summary in found:
            mark = "*" if self._sessions.here(summary) else " "
            when = f"{summary.updated_at.astimezone():%Y-%m-%d %H:%M}"
            count = f"{summary.messages} message" + (
                "" if summary.messages == 1 else "s"
            )
            print(
                f"  {mark} {clean_line(summary.id)}  {when}  {count}  "
                f"{self._shown(summary.cwd)}  {clean_line(summary.title)}",
                file=self._out,
            )
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
        if resumed.left_unsaved is not None:
            # Without id: its session could not even be created.
            what = f"session {clean_line(left)}" if left else "the conversation"
            print(
                f"warning: {what} was not saved, its last turns are lost: "
                f"{clean(resumed.left_unsaved)}",
                file=self._err,
                flush=True,
            )
        self._say(
            f"[resumed {clean_line(resumed.conversation.id or '')} · "
            f"{resumed.messages} messages · {clean_line(resumed.conversation.model)}]"
        )
        if resumed.other_cwd is not None:
            here = self._shown(self._sessions.cwd)
            self._say(
                f"[this session was in {self._shown(resumed.other_cwd)}; "
                f"tools work in {here}]"
            )
        if resumed.fallback_from is not None:
            self._say(
                f"[model {clean_line(resumed.fallback_from)} is of another provider; "
                f"using {clean_line(resumed.conversation.model)}]"
            )
        if resumed.interrupted:
            self._say("[the last answer was interrupted]")
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
        summary = report.summary
        if not summary.turns:
            self._say("(no turns in the trace)")
        else:
            for line in _summary_lines(summary):
                self._say(line)
        self._say(f"[trace: {self._shown(report.location)}]")

    def _shown(self, cwd: str) -> str:
        """A directory, with `~` for the home, clean."""
        path = PurePath(cwd)
        if path.is_relative_to(self._home):
            relative = path.relative_to(self._home)
            return clean_line("~" if relative == PurePath() else f"~/{relative}")
        return clean_line(cwd)

    def _say(self, text: str) -> None:
        print(f"  {text}", file=self._out, flush=True)


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
    at_least = "≥" if summary.uncosted_turns else ""
    lines.append(
        f"total: {usage.input_tokens} in · {usage.output_tokens} out · "
        f"{at_least}{usd(summary.cost)}"
    )
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
