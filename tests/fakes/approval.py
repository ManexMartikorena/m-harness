"""An `ApprovalGate` that answers from a script (spec hito 5, §3.1)."""

from collections.abc import Iterable

from mharness.domain.approval import ApprovalRequest, Decision


class FakeApproval:
    """Answers each request with the next decision of the script.

    Every request received is kept in `requests`. Being asked more times than
    scripted fails the test.
    """

    def __init__(self, decisions: Iterable[Decision] = ()) -> None:
        self._decisions = list(decisions)
        self.requests: list[ApprovalRequest] = []

    async def decide(self, request: ApprovalRequest) -> Decision:
        self.requests.append(request)
        if not self._decisions:
            raise AssertionError(
                f"FakeApproval: script exhausted at request {len(self.requests)}"
            )
        return self._decisions.pop(0)
