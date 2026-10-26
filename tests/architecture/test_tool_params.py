"""Every tool rejects arguments it does not have (spec
mejora-2026-10-26-deuda-pre-hito-6, B2): an ignored field would show in the
call as if it counted."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from mharness.bootstrap import _tools
from mharness.domain.model import ToolSpec

TOOLS = _tools(Path.cwd(), {}).specs()


@pytest.mark.parametrize("spec", TOOLS, ids=lambda spec: spec.name)
def test_the_schema_forbids_extra_fields(spec: ToolSpec) -> None:
    assert spec.input_schema["additionalProperties"] is False


def test_there_are_seven() -> None:
    assert len(TOOLS) == 7


def test_an_extra_field_is_an_error() -> None:
    tool = _tools(Path.cwd(), {}).get("run_command")
    assert tool is not None

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        tool.params.model_validate({"command": "ls", "timeout_seconds": 600})
