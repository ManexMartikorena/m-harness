"""The limits of one turn (spec hito 8, §1.1).

Code, not prompt: the loop checks them, and the model cannot change them.
Steps, cost and tokens are checked before each call to the model, with what
the turn spent so far, so a turn can pass one of them by one call at most.
The time is checked while the loop waits.
"""

from pydantic import BaseModel, Field

from mharness.domain.money import Usd

# Calls to the model in one turn, unless said otherwise.
MAX_STEPS = 25


class TurnLimits(BaseModel, frozen=True):
    # Calls to the model.
    max_steps: int = Field(default=MAX_STEPS, ge=1)
    # USD spent in the turn. A call without a known cost stops it: a limit
    # of money that cannot be checked is not a limit (decision 7).
    max_cost: Usd | None = None
    # Input and output tokens, summed over the turn's calls.
    max_tokens: int | None = Field(default=None, ge=1)
    # Seconds of the clock the loop may wait in the turn.
    timeout: float | None = Field(default=None, gt=0)
