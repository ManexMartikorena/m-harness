"""What a line is: a command for maha, or text for the model (spec hito 6,
§1.8)."""

import re
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TextIO

from mharness.adapters.cli.input import Discard, ReadLine
from mharness.adapters.cli.text import clean, clean_line
from mharness.application.sessions import Conversation, Sessions
from mharness.domain.session import SessionError

# What each command does, for /help.
COMMANDS = {
    "sessions": "/sessions — the recent sessions, of every directory",
    "resume": "/resume [ID] — resume a session; without ID, the last one here",
    "delete": "/delete ID — delete a session",
    "model": "/model [ID] — show the model, or change it",
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
        read: ReadLine,
        discard: Discard | None,
        out: TextIO,
        err: TextIO,
        home: Path,
    ) -> None:
        self._sessions = sessions
        self.conversation = conversation
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
                case "model":
                    await self._model(command.argument)
                case _:
                    self._say(f"unknown command: /{command.name} (see /help)")
        except SessionError as exc:
            message = str(exc)
            if message == "no session in this directory":
                message += " (see /sessions)"
            print(f"error: {clean(message)}", file=self._err, flush=True)
        self.warn_unsaved()

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
        resumed = await self._sessions.resume(session, current=self.conversation)
        self.conversation = resumed.conversation
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

    async def _delete(self, session: str | None) -> None:
        if session is None:
            self._say("usage: /delete ID")
            return
        if session == self.conversation.id:
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

    def _shown(self, cwd: str) -> str:
        """A directory, with `~` for the home, clean."""
        path = PurePath(cwd)
        if path.is_relative_to(self._home):
            relative = path.relative_to(self._home)
            return clean_line("~" if relative == PurePath() else f"~/{relative}")
        return clean_line(cwd)

    def _say(self, text: str) -> None:
        print(f"  {text}", file=self._out, flush=True)
