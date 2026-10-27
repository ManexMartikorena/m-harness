"""Trace records and the masking of credentials (spec hito 7, §1.7, §1.8 and
§4.1.2), without the disk."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from mharness.domain.agent_events import (
    ApprovalRequested,
    ModelCallFinished,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
    TurnStarted,
)
from mharness.domain.approval import ApprovalRequest
from mharness.domain.messages import ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.trace import (
    REDACTED,
    Secrets,
    TraceEvent,
    TraceRecord,
    TurnFailed,
    TurnInterrupted,
    known_secrets,
    mask,
    redact,
)

AT = datetime(2026, 10, 27, 9, 15, 4, 120000, tzinfo=UTC)
SESSION = "20261027-091502-3fa2"
KEY = "sk-inventada-0000000000000000"
CALL = ToolCallBlock(id="c1", name="run_command", arguments='{"command": "echo hola"}')


def pem(label: str, body: str) -> str:
    """A made-up PEM block. Built here, not written whole, so that gitleaks
    does not take the test data for a real key."""
    dashes = "-" * 5
    return f"{dashes}BEGIN {label}{dashes}\n{body}\n{dashes}END {label}{dashes}"


# Made up, with the shape of each kind of credential.
SHAPES = [
    "sk-inventada-1234567890",
    "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv",
    "ghp_" + "A" * 36,
    "gho_" + "b1" * 18,
    "github_pat_" + "C" * 30,
    "AKIA" + "ABCDEFGHIJKLMNOP",
    "xoxb-1234567890-abcdefghij",
    "AIza" + "D" * 35,
    pem("OPENSSH PRIVATE KEY", "AAAA\nBBBB"),
    pem("PRIVATE KEY", "CCCC"),
]


# mask()


def test_a_known_value_is_masked() -> None:
    assert mask(f"Authorization: Bearer {KEY}!", Secrets({KEY})) == (
        f"Authorization: Bearer {REDACTED}!"
    )


@pytest.mark.parametrize("secret", SHAPES)
def test_each_shape_of_credential_is_masked(secret: str) -> None:
    assert mask(f"antes {secret} después", Secrets()) == f"antes {REDACTED} después"


def test_several_in_one_text() -> None:
    text = f"{KEY} y {SHAPES[2]} y otra vez {KEY}"

    assert (
        mask(text, Secrets({KEY})) == f"{REDACTED} y {REDACTED} y otra vez {REDACTED}"
    )


def test_nothing_to_mask_stays_the_same() -> None:
    text = "sk-corto, skill, AKIA a medias, ghp_ sin más; ñandú"

    assert mask(text, Secrets()) == text


def test_a_short_known_value_is_not_masked() -> None:
    # "secret" or "1234" would mask half the trace (false positives).
    assert mask("el valor es 12345678", Secrets({"12345678"})) == "el valor es 12345678"


def test_the_longer_known_value_goes_first() -> None:
    long, short = "abcdefghij-klmnop", "abcdefghij"

    assert mask(f"{long} {short}", Secrets({short, long})) == f"{REDACTED} {REDACTED}"


def test_a_private_key_cut_before_its_end_is_masked_to_the_end() -> None:
    # read_file with a limit, or `head id_rsa` (audit of hito 7, 4).
    cut = pem("OPENSSH PRIVATE KEY", "AAAA\nBBBB").rsplit("\n", 1)[0]

    assert mask(f"la clave:\n{cut}", Secrets()) == f"la clave:\n{REDACTED}"


@pytest.mark.parametrize(
    ("secret", "written"),
    [
        ('con"comillas-dentro', 'con\\"comillas-dentro'),
        ("con\\barra-invertida", "con\\\\barra-invertida"),
        ("con/barra-normal", "con\\/barra-normal"),
        ("contraseña-larga", "contrase\\u00f1a-larga"),
    ],
)
def test_a_known_value_escaped_in_json_is_masked(secret: str, written: str) -> None:
    # The arguments of a call are JSON text written by the model (audit of
    # hito 7, 5).
    arguments = f'{{"command": "echo {written}"}}'

    assert mask(arguments, Secrets({secret})) == (f'{{"command": "echo {REDACTED}"}}')


# known_secrets()


def test_known_secrets_take_variables_that_look_like_credentials() -> None:
    env = {
        "OPENCODE_API_KEY": KEY,
        "GITHUB_TOKEN": "ghp_token_value_123",
        "db_password": "contraseña-larga",
        "AWS_SECRET_ACCESS_KEY": "aws-secret-value-1",
        "HOME": "/home/ana/un-camino-largo",
        "SHORT_KEY": "12345678",
    }

    assert known_secrets(env, also=["clave-del-proveedor"]) == {
        KEY,
        "ghp_token_value_123",
        "contraseña-larga",
        "aws-secret-value-1",
        "clave-del-proveedor",
    }


def test_known_secrets_skip_an_empty_extra() -> None:
    assert known_secrets({}, also=[None, ""]) == set()


# TraceRecord and redact()


def record(event: TraceEvent) -> TraceRecord:
    return TraceRecord(at=AT, session=SESSION, event=event)


EVENTS: list[TraceEvent] = [
    TurnStarted(text="Arregla el test"),
    ToolCallProposed(call=CALL),
    ApprovalRequested(
        call=CALL,
        request=ApprovalRequest(
            tool="run_command", title="run", detail="echo hola", scope="run"
        ),
    ),
    ToolFinished(
        call=CALL,
        result=ToolResultBlock(call_id="c1", content="hola"),
        summary="exit 0",
        duration=0.12,
        decision="once",
    ),
    ModelCallFinished(usage=Usage(input_tokens=10), model="m", cost=Decimal("0.01")),
    TurnFinished(
        reason="end_turn", usage=Usage(), tool_calls=1, steps=2, cost=Decimal("0.01")
    ),
    TurnFailed(kind="ModelUnavailableError", message="HTTP 503"),
    TurnInterrupted(),
]


@pytest.mark.parametrize("event", EVENTS)
def test_every_record_goes_through_json(event: TraceEvent) -> None:
    line = record(event).model_dump_json()

    assert TraceRecord.model_validate_json(line) == record(event)


def test_a_record_line_as_the_spec_shows_it() -> None:
    line = record(TurnStarted(text="Hola")).model_dump(mode="json")

    assert line == {
        "at": "2026-10-27T09:15:04.120000Z",
        "session": SESSION,
        "event": {"type": "turn_started", "text": "Hola"},
    }


def test_a_text_delta_is_not_a_trace_event() -> None:
    with pytest.raises(ValidationError):
        TraceRecord.model_validate(
            {
                "at": AT.isoformat(),
                "session": SESSION,
                "event": {"type": "text_delta", "text": "Ho"},
            }
        )


def test_redact_masks_every_text_of_the_record() -> None:
    call = ToolCallBlock(
        id="c1", name="run_command", arguments=f'{{"command": "echo {KEY}"}}'
    )
    finished = ToolFinished(
        call=call,
        result=ToolResultBlock(call_id="c1", content=f"{SHAPES[2]}\n"),
        summary=f"saca {KEY}",
        duration=0.1,
    )

    masked = redact(record(finished), Secrets({KEY}))

    assert isinstance(masked.event, ToolFinished)
    assert KEY not in masked.model_dump_json()
    assert SHAPES[2] not in masked.model_dump_json()
    assert masked.event.call.arguments == f'{{"command": "echo {REDACTED}"}}'
    assert masked.event.result.content == f"{REDACTED}\n"
    assert masked.event.duration == 0.1


def test_redact_leaves_a_clean_record_as_it_was() -> None:
    clean = record(TurnFailed(kind="ModelUnavailableError", message="HTTP 503"))

    assert redact(clean, Secrets({KEY})) == clean
