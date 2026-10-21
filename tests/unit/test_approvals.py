from mharness.application.approvals import SessionApprovals
from mharness.domain.approval import ApprovalRequest

EDIT = ApprovalRequest(
    tool="edit_file",
    title="edit notas.txt",
    detail="-Comprar pan\n+Comprar pan y leche",
    scope="edit_file",
)
PYTEST = ApprovalRequest(
    tool="run_command",
    title="run: uv run pytest",
    detail="uv run pytest",
    scope="run_command:uv run pytest",
)
OUTSIDE = ApprovalRequest(
    tool="read_file",
    title="read /etc/hostname",
    detail="/etc/hostname",
    scope=None,
    warning="outside the working directory",
)


def test_nothing_is_approved_at_the_start() -> None:
    approvals = SessionApprovals()

    assert not approvals.covers(EDIT)
    assert not approvals.covers(OUTSIDE)


def test_session_keeps_the_scope() -> None:
    approvals = SessionApprovals()
    approvals.record(EDIT, "session")
    other_file = EDIT.model_copy(update={"title": "edit lista.txt", "detail": "-a\n+b"})

    # The scope covers every edit, not only the file of the first one.
    assert approvals.covers(EDIT)
    assert approvals.covers(other_file)


def test_a_scope_covers_only_itself() -> None:
    approvals = SessionApprovals()
    approvals.record(PYTEST, "session")
    other_command = PYTEST.model_copy(
        update={"title": "run: ls", "detail": "ls", "scope": "run_command:ls"}
    )

    assert approvals.covers(PYTEST)
    assert not approvals.covers(other_command)
    assert not approvals.covers(EDIT)


def test_once_and_deny_keep_nothing() -> None:
    approvals = SessionApprovals()
    approvals.record(EDIT, "once")
    approvals.record(PYTEST, "deny")

    assert not approvals.covers(EDIT)
    assert not approvals.covers(PYTEST)


def test_a_request_without_scope_is_never_kept() -> None:
    # Outside the working directory or a secret: always one by one.
    approvals = SessionApprovals()
    approvals.record(OUTSIDE, "session")

    assert not approvals.covers(OUTSIDE)
