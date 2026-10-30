"""How long to wait before calling the model again (spec hito 8, §1.14).

```
attempt 1 → 1 s, attempt 2 → 2 s, attempt 3 → 4 s   (each + up to 25 %)
Retry-After: 30 → 30 s, Retry-After: 600 → 60 s
```

Pure: the chance comes from `random`, which the tests fix. The loop does
the waiting.
"""

import random as _random
from collections.abc import Callable
from dataclasses import dataclass, field

# Retries after the first call fails.
MAX_RETRIES = 3
# The first wait, in seconds; each next one doubles.
BASE_DELAY = 1.0
# Up to this share of the wait is added by chance, so that many clients do
# not all come back at the same time (jitter).
JITTER = 0.25
# The longest `Retry-After` honoured, in seconds.
MAX_RETRY_AFTER = 60.0


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = MAX_RETRIES
    base_delay: float = BASE_DELAY
    jitter: float = JITTER
    max_retry_after: float = MAX_RETRY_AFTER
    # A number in [0, 1).
    random: Callable[[], float] = field(default=_random.random, compare=False)

    def delay(self, attempt: int, retry_after: float | None = None) -> float | None:
        """The wait before retry number `attempt` (from 1), or None when no
        retry is left. The provider's `Retry-After` wins, cut to
        `max_retry_after`: it knows when it can answer."""
        if not 1 <= attempt <= self.max_retries:
            return None
        if retry_after is not None:
            return min(max(retry_after, 0.0), self.max_retry_after)
        wait = self.base_delay * 2.0 ** (attempt - 1)
        return wait * (1 + self.jitter * self.random())


# For whoever must not retry: the tests of a single failure, for example.
NO_RETRIES = RetryPolicy(max_retries=0)
