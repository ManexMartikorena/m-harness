"""The question in the terminal (spec hito 5, §1.10 and §4.6)."""

import io

import pytest

from mharness.adapters.cli.approval import DenyAll, TerminalApproval
from mharness.domain.approval import ApprovalRequest, Decision
from mharness.ports.approval import ApprovalGate
from tests.fakes.terminal import ScriptedInput

EDIT = ApprovalRequest(
    tool="edit_file",
    title="edit notas.txt",
    detail="@@ -1 +1 @@\n-Comprar pan\n+Comprar pan y leche",
    scope="edit_file",
)
OUTSIDE = ApprovalRequest(
    tool="read_file",
    title="read /etc/hostname",
    detail="/etc/hostname",
    scope=None,
    warning="outside the working directory",
)
WITH_ALWAYS = "  └ Allow? [y] yes · [a] always this session · [n] no: "
WITHOUT_ALWAYS = "  └ Allow? [y] yes · [n] no: "


async def ask(
    request: ApprovalRequest, *answers: str, color: bool = False
) -> tuple[Decision, str]:
    out = io.StringIO()
    gate = TerminalApproval(ScriptedInput(*answers), out, color=color)
    return await gate.decide(request), out.getvalue()


def test_both_satisfy_the_port() -> None:
    # mypy checks these assignments against the Protocol.
    terminal: ApprovalGate = TerminalApproval(ScriptedInput(), io.StringIO())
    deny: ApprovalGate = DenyAll(io.StringIO())

    assert terminal is not None
    assert deny is not None


async def test_it_shows_the_question_and_yes_is_once() -> None:
    decision, shown = await ask(EDIT, "y")

    assert decision == "once"
    assert shown == (
        "  ┌ edit notas.txt\n"
        "  │ @@ -1 +1 @@\n"
        "  │ -Comprar pan\n"
        "  │ +Comprar pan y leche\n" + WITH_ALWAYS
    )


@pytest.mark.parametrize(
    ("answer", "decision"),
    [
        ("y", "once"),
        ("YES", "once"),
        ("s", "once"),
        ("sí", "once"),
        (" a ", "session"),
        ("n", "deny"),
        ("no", "deny"),
    ],
)
async def test_the_answers(answer: str, decision: Decision) -> None:
    assert (await ask(EDIT, answer))[0] == decision


async def test_another_answer_asks_again() -> None:
    decision, shown = await ask(EDIT, "quizá", "", "n")

    assert decision == "deny"
    assert shown.count(WITH_ALWAYS) == 3


async def test_end_of_input_denies() -> None:
    decision, shown = await ask(EDIT)

    assert decision == "deny"
    assert shown.endswith(WITH_ALWAYS + "\n")


async def test_without_a_scope_always_is_not_offered() -> None:
    decision, shown = await ask(OUTSIDE, "a", "y")

    assert decision == "once"
    assert "always" not in shown
    assert shown.count(WITHOUT_ALWAYS) == 2


async def test_the_warning_has_its_own_line_in_yellow_with_color() -> None:
    _, plain = await ask(OUTSIDE, "n")
    _, colored = await ask(OUTSIDE, "n", color=True)

    assert "  │ ! outside the working directory\n" in plain
    assert "  │ \x1b[33m! outside the working directory\x1b[0m\n" in colored


async def test_a_long_detail_is_cut() -> None:
    detail = "\n".join(["x" * 300, *(f"línea {n}" for n in range(70))])
    request = EDIT.model_copy(update={"detail": detail})

    _, shown = await ask(request, "n")

    lines = shown.splitlines()
    assert lines[1] == "  │ " + "x" * 200 + "…"
    assert lines[60] == "  │ línea 58"
    assert lines[61] == "  │ … [11 more lines]"


async def test_control_characters_cannot_fake_the_question() -> None:
    # Spec hito 5, §1.10: a file or an argument could repaint the screen.
    request = ApprovalRequest(
        tool="edit_file",
        title="edit a\x1b[2K\rb",
        detail="-uno\r+dos",
        scope="edit_file",
        warning="x\x1b[0m",
    )

    _, shown = await ask(request, "n")

    assert "\x1b" not in shown
    assert "\r" not in shown
    assert "  ┌ edit a\\x1b[2K\\x0db\n" in shown


async def test_deny_all_denies_without_asking() -> None:
    out = io.StringIO()

    decision = await DenyAll(out).decide(EDIT)

    assert decision == "deny"
    assert out.getvalue() == "  (denied: input is not a terminal)\n"
