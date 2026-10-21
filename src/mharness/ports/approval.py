"""Port to whoever approves a tool call (DESIGN §6, spec hito 5, §1.2)."""

from typing import Protocol

from mharness.domain.approval import ApprovalRequest, Decision


class ApprovalGate(Protocol):
    """Decides on a tool call: once, for the whole session, or deny.

    The loop asks it; the model never does. Permission is code, not prompt.
    """

    async def decide(self, request: ApprovalRequest) -> Decision: ...
