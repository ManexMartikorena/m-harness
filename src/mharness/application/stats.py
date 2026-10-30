"""What `maha stats` adds up: cost and tokens by day and model, from every
trace (spec hito 8, §1.15).

```
2026-10-30  glm-5.3-flash   12 calls  52360 in  4100 out  $0.0123
```

The traces are the record of what each call cost, also of the sessions of
other directories and of `maha -p`. A deleted session takes its trace, and
its cost, with it.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, tzinfo
from decimal import Decimal

from mharness.domain.agent_events import ModelCallFinished
from mharness.domain.model import Usage
from mharness.ports.tracing import TraceSink


@dataclass(frozen=True)
class DayModel:
    """The calls to one model in one day."""

    day: date
    model: str
    calls: int
    usage: Usage
    # Of the calls with a price; `uncosted` says how many had none.
    cost: Decimal
    uncosted: int


async def daily(
    traces: TraceSink, *, since: date | None = None, tz: tzinfo | None = None
) -> list[DayModel]:
    """A row per day and model that answered, oldest first; only from
    `since`, if given. The day is that of `tz` (the local one by default),
    as the person counts them. Raises `TraceError` if a trace cannot be
    read."""
    calls: dict[tuple[date, str], list[ModelCallFinished]] = defaultdict(list)
    for session in await traces.sessions():
        for record in await traces.read(session):
            event = record.event
            if not isinstance(event, ModelCallFinished):
                continue
            day = record.at.astimezone(tz).date()
            if since is None or day >= since:
                calls[day, event.model].append(event)
    return [
        DayModel(
            day=day,
            model=model,
            calls=len(found),
            usage=sum((event.usage for event in found), Usage()),
            cost=sum(
                (event.cost for event in found if event.cost is not None), Decimal(0)
            ),
            uncosted=sum(1 for event in found if event.cost is None),
        )
        for (day, model), found in sorted(calls.items())
    ]
