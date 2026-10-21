import pytest
from pydantic import ValidationError

from mharness.domain.approval import ApprovalRequest
from mharness.ports.approval import ApprovalGate
from tests.fakes.approval import FakeApproval

REQUEST = ApprovalRequest(
    tool="edit_file",
    title="edit notas.txt",
    detail="-Comprar pan\n+Comprar pan y leche",
    scope="edit_file",
)


def test_fake_satisfies_the_port() -> None:
    # mypy checks this assignment against the Protocol.
    gate: ApprovalGate = FakeApproval()

    assert gate is not None


def test_a_request_has_no_warning_by_default_and_is_frozen() -> None:
    assert REQUEST.warning is None
    with pytest.raises(ValidationError):
        REQUEST.scope = None  # type: ignore[misc]


async def test_answers_the_script_in_order_and_keeps_the_requests() -> None:
    gate = FakeApproval(["once", "deny"])
    outside = REQUEST.model_copy(
        update={"scope": None, "warning": "outside the working directory"}
    )

    assert await gate.decide(REQUEST) == "once"
    assert await gate.decide(outside) == "deny"
    assert gate.requests == [REQUEST, outside]


async def test_asking_more_than_scripted_fails() -> None:
    gate = FakeApproval(["session"])
    await gate.decide(REQUEST)

    with pytest.raises(AssertionError, match="script exhausted at request 2"):
        await gate.decide(REQUEST)
