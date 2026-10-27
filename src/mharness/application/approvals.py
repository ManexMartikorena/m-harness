"""What the user approved for the whole session (spec hito 5, §1.3), and
what is approved when nobody can be asked (spec hito 8, §1.2).

Answering "always this session" keeps the scope of the request; later
requests with the same scope run without asking until maha ends. Nothing is
kept on disk: the approvals die with the process.
"""

from collections.abc import Iterable

from mharness.domain.approval import ApprovalRequest, Decision


class SessionApprovals:
    """The scopes approved for the session, in memory.

    A request without a scope (outside the working directory, a secret) is
    never kept nor covered: it is asked one by one (DESIGN §10).
    """

    def __init__(self) -> None:
        self._scopes: set[str] = set()

    def covers(self, request: ApprovalRequest) -> bool:
        """Whether the request was already approved for the session."""
        return request.scope is not None and request.scope in self._scopes

    def record(self, request: ApprovalRequest, decision: Decision) -> None:
        """Keep the scope of the request if the user approved it for the
        session. `once` and `deny` keep nothing."""
        if decision == "session" and request.scope is not None:
            self._scopes.add(request.scope)


class AllowList:
    """An `ApprovalGate` without a person (`maha -p`, evals): runs once the
    calls of the tools named, and denies the rest.

    A request without a scope is always denied: with a person it is asked
    every time (outside the working directory, a secret, a file that runs
    code), and here there is nobody to ask. The list comes from the command
    line or from an eval task, never from a configuration file: a foreign
    repository cannot grant itself permissions.
    """

    def __init__(self, tools: Iterable[str]) -> None:
        self.tools = frozenset(tools)

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.scope is not None and request.tool in self.tools:
            return "once"
        return "deny"
