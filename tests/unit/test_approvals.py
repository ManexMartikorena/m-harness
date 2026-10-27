from mharness.application.approvals import AllowList, SessionApprovals
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


# Without a person (spec hito 8, §1.2): `--allow TOOL` approves what has a
# scope; what with a person asks every time is always denied.


def question(tool: str, scope: str | None) -> ApprovalRequest:
    return ApprovalRequest(tool=tool, title=f"{tool} x", detail="", scope=scope)


async def test_allow_list_approves_once_a_listed_tool_with_a_scope() -> None:
    gate = AllowList(["write_file", "edit_file"])

    assert await gate.decide(question("edit_file", "edit_file")) == "once"
    assert await gate.decide(question("write_file", "write_file")) == "once"


async def test_allow_list_denies_what_asks_every_time_even_if_listed() -> None:
    # Outside the working directory, a secret, a file that runs code.
    gate = AllowList(["read_file", "edit_file"])

    assert await gate.decide(question("read_file", None)) == "deny"
    assert await gate.decide(question("edit_file", None)) == "deny"


async def test_allow_list_denies_a_tool_not_listed() -> None:
    gate = AllowList(["edit_file"])

    assert await gate.decide(question("run_command", "run: ls")) == "deny"
    assert await gate.decide(question("write_file", "write_file")) == "deny"


async def test_an_empty_allow_list_denies_everything() -> None:
    assert await AllowList([]).decide(question("edit_file", "edit_file")) == "deny"
