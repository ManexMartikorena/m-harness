from pathlib import Path

import pytest

from mharness.domain.commands import CommandResult
from mharness.ports.commands import CommandRunner
from tests.fakes.commands import FakeRunner, Ran

DONE = CommandResult(exit_code=0, output="ok\n", truncated=False, timed_out=False)


def test_fake_satisfies_the_port() -> None:
    # mypy checks this assignment against the Protocol.
    runner: CommandRunner = FakeRunner()

    assert runner is not None


async def test_answers_the_script_and_keeps_what_ran(tmp_path: Path) -> None:
    runner = FakeRunner([DONE])

    result = await runner.run("ls", cwd=tmp_path, time_limit=5, env={"PATH": "/bin"})

    assert result == DONE
    assert runner.ran == [Ran("ls", tmp_path, 5, {"PATH": "/bin"})]
    with pytest.raises(AssertionError, match="script exhausted"):
        await runner.run("ls", cwd=tmp_path, time_limit=5, env={})
