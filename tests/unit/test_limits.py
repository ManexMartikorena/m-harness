"""The default limits of a turn (spec hito 8, §1.1)."""

from mharness.domain.evals import TASK_LIMITS
from mharness.domain.limits import TurnLimits


def test_a_turn_has_fifty_steps_unless_said_otherwise() -> None:
    # Spec hito 11, §1.16: 25 while a long turn filled the context; with
    # the working budget, each step's cost is bounded.
    assert TurnLimits().max_steps == 50
    assert TASK_LIMITS.max_steps == 50
