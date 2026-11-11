"""The `maha` subcommands over the sessions and their traces (spec hito 8,
§1.15): what /sessions, /delete and /trace do, from the shell; the cost
of every session; and a session exported and imported.

```
$ maha sessions
* 20261030-101500-3fa2  2026-10-30 10:15  4 messages  ~/proyecto  Revisa…
$ maha sessions delete 20261030-101500-3fa2
deleted 20261030-101500-3fa2
```

Each returns the exit code: 0, or 1 with the error on stderr.
"""

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, TextIO

from pydantic import ValidationError

from mharness.adapters.cli.commands import session_lines, trace_lines
from mharness.adapters.cli.export import markdown
from mharness.adapters.cli.reports import stats_report
from mharness.adapters.cli.text import clean, clean_json, clean_line
from mharness.application.sessions import Sessions
from mharness.application.stats import daily
from mharness.domain.session import Session, SessionError
from mharness.domain.trace import TraceError
from mharness.ports.tracing import TraceSink

EXIT_OK = 0
EXIT_ERROR = 1

type ExportFormat = Literal["md", "json"]


async def list_sessions(
    sessions: Sessions, *, out: TextIO, home: Path, every: bool = False
) -> int:
    """`maha sessions`: the recent ones, of every directory; with `--all`,
    every one (audit after hito 10, P6)."""
    lines = await session_lines(
        sessions, home, every=every, see_all="maha sessions --all"
    )
    for line in lines:
        print(line, file=out)
    return EXIT_OK


async def delete_session(
    sessions: Sessions, session: str, *, out: TextIO, err: TextIO
) -> int:
    """`maha sessions delete ID`: the session and its trace, without asking:
    the id was written on purpose, as with `rm`."""
    try:
        await sessions.delete(session)
    except (SessionError, TraceError) as exc:
        return _fail(exc, err)
    print(f"deleted {clean_line(session)}", file=out)
    return EXIT_OK


async def show_trace(
    sessions: Sessions, session: str | None, *, out: TextIO, err: TextIO, home: Path
) -> int:
    """`maha trace [ID]`: what a session did and cost, as /trace; without
    id, the last session of this directory (spec hito 7, §11.5)."""
    try:
        target = session if session is not None else await sessions.last_here()
        report = await sessions.trace(target)
    except (SessionError, TraceError) as exc:
        return _fail(exc, err)
    for line in trace_lines(report, home):
        print(line, file=out)
    return EXIT_OK


async def show_stats(
    traces: TraceSink, *, days: int | None, today: date, out: TextIO, err: TextIO
) -> int:
    """`maha stats [--days N]`: cost and tokens by day and model; with
    `days`, only the last ones, today included."""
    # More days than the calendar holds is every day (audit of hito 8).
    back = None if days is None else min(days - 1, (today - date.min).days)
    since = None if back is None else today - timedelta(days=back)
    try:
        rows = await daily(traces, since=since)
    except TraceError as exc:
        return _fail(exc, err)
    stats_report(rows, days=days, out=out)
    return EXIT_OK


async def export_session(
    sessions: Sessions,
    session: str,
    *,
    output_format: ExportFormat,
    out: TextIO,
    err: TextIO,
) -> int:
    """`maha export ID [--format md|json]`: the conversation in Markdown, or
    the session in JSON, which `maha import` takes back."""
    try:
        found = await sessions.read(session)
    except SessionError as exc:
        return _fail(exc, err)
    if output_format == "json":
        # Escaped also to a file: the same JSON wherever it goes.
        out.write(clean_json(found.model_dump_json(indent=2)) + "\n")
    else:
        text = markdown(found)
        # As `maha -p`: clean to a terminal, as it is to a file.
        out.write(clean(text) if out.isatty() else text)
    out.flush()
    return EXIT_OK


async def import_session(
    sessions: Sessions, file: Path, *, out: TextIO, err: TextIO
) -> int:
    """`maha import FILE`: a session of `maha export --format json`, as a
    new session of this directory."""
    try:
        data = await asyncio.to_thread(_read_at_most, file, IMPORT_MAX_BYTES)
    except OSError as exc:
        return _fail(f"cannot read {file}: {exc.strerror}", err)
    if len(data) > IMPORT_MAX_BYTES:
        return _fail(f"{file} is larger than {_size(IMPORT_MAX_BYTES)}", err)
    try:
        session = Session.model_validate_json(data)
    except ValidationError as exc:
        problem = exc.errors(include_url=False, include_input=False)[0]
        where = ".".join(str(part) for part in problem["loc"])
        detail = f"{where}: {problem['msg']}" if where else problem["msg"]
        return _fail(f"{file} is not a session of maha export: {detail}", err)
    try:
        new = await sessions.import_session(session)
    except SessionError as exc:
        return _fail(exc, err)
    print(f"imported as {new} · maha -r {new} resumes it", file=out)
    return EXIT_OK


# The largest file `maha import` reads: a long session with its tool
# results is a few MiB (audit after hito 10, I15).
IMPORT_MAX_BYTES = 64 * 1024 * 1024


def _read_at_most(file: Path, limit: int) -> bytes:
    """The bytes of `file`, at most one more than `limit`."""
    with file.open("rb") as stream:
        return stream.read(limit + 1)


def _size(limit: int) -> str:
    mib, rest = divmod(limit, 1024 * 1024)
    return f"{mib} MiB" if mib and not rest else f"{limit} bytes"


def _fail(exc: Exception | str, err: TextIO) -> int:
    print(f"error: {clean(str(exc))}", file=err, flush=True)
    return EXIT_ERROR


def show_prompt(text: str, out: TextIO) -> None:
    """`maha prompt`: to a terminal, clean, as an AGENTS.md of a foreign
    repository could repaint it or write to the clipboard (audit after hito
    10, I1); to a file or a pipe, as the model gets it, as with `cat`."""
    print(clean(text) if out.isatty() else text, file=out)
