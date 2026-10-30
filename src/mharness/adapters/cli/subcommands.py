"""The `maha` subcommands over the sessions and their traces (spec hito 8,
§1.15): what /sessions, /delete and /trace do, from the shell.

```
$ maha sessions
* 20261030-101500-3fa2  2026-10-30 10:15  4 messages  ~/proyecto  Revisa…
$ maha sessions delete 20261030-101500-3fa2
deleted 20261030-101500-3fa2
```

Each returns the exit code: 0, or 1 with the error on stderr.
"""

from pathlib import Path
from typing import TextIO

from mharness.adapters.cli.commands import session_lines
from mharness.adapters.cli.text import clean, clean_line
from mharness.application.sessions import Sessions
from mharness.domain.session import SessionError
from mharness.domain.trace import TraceError

EXIT_OK = 0
EXIT_ERROR = 1


async def list_sessions(sessions: Sessions, *, out: TextIO, home: Path) -> int:
    """`maha sessions`: the recent ones, of every directory."""
    for line in await session_lines(sessions, home):
        print(line, file=out)
    return EXIT_OK


async def delete_session(
    sessions: Sessions, session: str, *, out: TextIO, err: TextIO
) -> int:
    """`maha sessions delete ID`: the session and its trace, without asking:
    the id was written on purpose, as with `rm`."""
    current = await sessions.start()
    try:
        await sessions.delete(session, current=current)
    except (SessionError, TraceError) as exc:
        return _fail(exc, err)
    finally:
        await current.close()
    print(f"deleted {clean_line(session)}", file=out)
    return EXIT_OK


def _fail(exc: Exception, err: TextIO) -> int:
    print(f"error: {clean(str(exc))}", file=err, flush=True)
    return EXIT_ERROR
