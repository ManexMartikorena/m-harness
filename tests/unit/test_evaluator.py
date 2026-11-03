"""`Evaluator`: runs the battery, checks each run and keeps the provider's
failures apart (spec hito 8, §1.5 to §1.9), with fakes."""

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from mharness.application.evals import Evaluator, choose
from mharness.application.sessions import Conversation
from mharness.domain.commands import CommandResult
from mharness.domain.errors import (
    ModelAuthError,
    ModelError,
    ModelRateLimitError,
    ModelRequestError,
    ModelResponseError,
    ModelUnavailableError,
)
from mharness.domain.evals import Check, Task, TaskRun
from mharness.domain.model import Usage
from tests.adapters.test_print_mode import crashing_second
from tests.fakes.commands import FakeRunner
from tests.fakes.evals import MemoryEvalSuite
from tests.fakes.model import FakeModelClient, Step, reply
from tests.fakes.sessions import MemorySessionStore
from tests.unit.test_sessions import World

FIXTURES = {"tienda": {"pyproject.toml": 'version = "1.4.2"\n'}}
ENV = {"PATH": "/usr/bin"}


def task(id: str = "01", check: Check | None = None, split: str = "train") -> Task:
    return Task.model_validate(
        {
            "id": id,
            "instruction": "¿Qué versión?",
            "fixture": "tienda",
            "split": split,
            "check": check or Check(answer_contains=["1.4.2"]),
        }
    )


def opener(
    script: Callable[[Task, str], list[Step]],
    opened: list[tuple[str, str, Path]] | None = None,
) -> Callable[[Task, str, Path], object]:
    """Opens each run's conversation on a model that answers `script`."""

    @asynccontextmanager
    async def open_run(t: Task, model: str, path: Path) -> AsyncIterator[Conversation]:
        if opened is not None:
            opened.append((t.id, model, path))
        world = World(
            MemorySessionStore(), FakeModelClient(script(t, model)), model=model
        )
        conversation = await world.sessions.start()
        try:
            yield conversation
        finally:
            await conversation.close()

    return open_run


def evaluator(
    script: Callable[[Task, str], list[Step]],
    *tasks: Task,
    runner: FakeRunner | None = None,
    opened: list[tuple[str, str, Path]] | None = None,
) -> tuple[Evaluator, MemoryEvalSuite]:
    suite = MemoryEvalSuite(list(tasks), FIXTURES)
    return (
        Evaluator(suite, opener(script, opened), runner or FakeRunner(), ENV),  # type: ignore[arg-type]
        suite,
    )


def says(text: str, tokens: int = 100) -> Callable[[Task, str], list[Step]]:
    return lambda t, m: [reply(text, usage=Usage(input_tokens=tokens))]


async def test_an_answer_that_passes_its_check() -> None:
    subject, _ = evaluator(says("La versión es 1.4.2."), task())

    [run] = await subject.run([task()], ["glm-5.3-flash"])

    assert run == TaskRun(
        task="01",
        split="train",
        model="glm-5.3-flash",
        attempt=1,
        outcome="pass",
        reason="end_turn",
        steps=1,
        tool_calls=0,
        tool_errors=0,
        tokens=100,
        cost=None,
        duration=run.duration,
    )


async def test_an_answer_that_fails_says_why() -> None:
    subject, _ = evaluator(says("No lo sé."), task())

    [run] = await subject.run([task()], ["m"])

    assert (run.outcome, run.detail) == ("fail", "the answer does not contain '1.4.2'")


async def test_a_file_of_the_copy_is_checked() -> None:
    good = task(check=Check(file="pyproject.toml", contains=["1.4.2"]))
    bad = task("02", check=Check(file="pyproject.toml", absent=["1.4.2"]))
    missing = task("03", check=Check(file="nope.txt", contains=["x"]))
    subject, _ = evaluator(says("Hecho."), good, bad, missing)

    runs = await subject.run([good, bad, missing], ["m"])

    assert [(r.outcome, r.detail) for r in runs] == [
        ("pass", None),
        ("fail", "pyproject.toml still contains '1.4.2'"),
        ("fail", "nope.txt does not exist"),
    ]


async def test_the_command_runs_in_the_copy_and_must_end_with_zero() -> None:
    check = Check(command="python3 -m unittest -q")
    runner = FakeRunner(
        [
            CommandResult(exit_code=0, output="OK", truncated=False, timed_out=False),
            CommandResult(
                exit_code=1,
                output="FAILED (failures=1)",
                truncated=False,
                timed_out=False,
            ),
        ]
    )
    opened: list[tuple[str, str, Path]] = []
    subject, _ = evaluator(
        says("Hecho."), task(check=check), runner=runner, opened=opened
    )

    runs = await subject.run([task(check=check)], ["m"], repeat=2)

    assert [r.outcome for r in runs] == ["pass", "fail"]
    assert runs[1].detail == "the check exited with 1:\nFAILED (failures=1)"
    assert [r.cwd for r in runner.ran] == [path for *_, path in opened]
    assert runner.ran[0].env == ENV


async def test_a_provider_failure_is_an_error_and_is_not_checked() -> None:
    def script(t: Task, m: str) -> list[Step]:
        return [ModelRateLimitError("429 Too Many Requests")]

    # FakeRunner without a script fails the test if the check runs.
    subject, _ = evaluator(script, task(check=Check(command="false")))

    [run] = await subject.run([task(check=Check(command="false"))], ["m"])

    assert (run.outcome, run.detail) == ("error", "429 Too Many Requests")


async def test_errors_can_be_run_again_once() -> None:
    calls = 0

    def script(t: Task, m: str) -> list[Step]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return [ModelRateLimitError("429 Too Many Requests")]
        return [reply("1.4.2")]

    seen: list[TaskRun] = []
    subject, _ = evaluator(script, task())

    [run] = await subject.run([task()], ["m"], retry_errors=True, on_run=seen.append)

    assert (run.outcome, run.attempt) == ("pass", 1)
    assert [r.outcome for r in seen] == ["error", "pass"]


async def test_every_model_task_and_repetition_in_order() -> None:
    tasks = [task("01"), task("02")]
    subject, suite = evaluator(says("1.4.2"), *tasks)

    runs = await subject.run(tasks, ["a", "b"], repeat=2, jobs=3)

    assert [(r.model, r.task, r.attempt) for r in runs] == [
        ("a", "01", 1),
        ("a", "01", 2),
        ("a", "02", 1),
        ("a", "02", 2),
        ("b", "01", 1),
        ("b", "01", 2),
        ("b", "02", 1),
        ("b", "02", 2),
    ]
    # Each run, on its own copy.
    assert len(set(suite.workspaces)) == 8


async def test_no_more_runs_at_once_than_jobs() -> None:
    running = 0
    most = 0
    release = asyncio.Event()

    @asynccontextmanager
    async def open_run(t: Task, model: str, path: Path) -> AsyncIterator[Conversation]:
        nonlocal running, most
        running += 1
        most = max(most, running)
        if running == 2:
            release.set()
        await release.wait()
        world = World(MemorySessionStore(), FakeModelClient([reply("1.4.2")]))
        conversation = await world.sessions.start()
        try:
            yield conversation
        finally:
            running -= 1
            await conversation.close()

    suite = MemoryEvalSuite([task()], FIXTURES)
    subject = Evaluator(suite, open_run, FakeRunner(), ENV)

    runs = await subject.run([task()], ["m"], repeat=6, jobs=2)

    assert most == 2
    assert all(r.outcome == "pass" for r in runs)


def test_choose_by_split_and_by_id() -> None:
    tasks = [task("01"), task("02", split="validation"), task("03")]

    assert [t.id for t in choose(tasks, "train")] == ["01", "03"]
    assert [t.id for t in choose(tasks, "validation")] == ["02"]
    assert [t.id for t in choose(tasks, "all")] == ["01", "02", "03"]
    assert [t.id for t in choose(tasks, "all", only=["03", "01"])] == ["01", "03"]


async def test_a_run_that_crashes_does_not_take_the_others_with_it() -> None:
    # Audit of hito 8: one unexpected exception threw away the whole
    # battery, paid calls included.
    def script(t: Task, m: str) -> list[Step]:
        if t.id == "02":
            raise PermissionError("cannot read the fixture")
        return [reply("1.4.2")]

    subject, _ = evaluator(script, task("01"), task("02"))

    first, second = await subject.run([task("01"), task("02")], ["m"])

    assert first.outcome == "pass"
    assert (second.outcome, second.reason) == ("error", "internal")
    assert second.detail == "PermissionError: cannot read the fixture"


async def test_what_finished_keeps_the_last_try_of_each_run() -> None:
    # Review of the audit of hito 8: Ctrl+C after a retry kept the error and
    # its retry, as two runs of attempt 1. `finished` is what Ctrl+C keeps.
    calls = 0

    def script(t: Task, m: str) -> list[Step]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return [ModelRateLimitError("429 Too Many Requests")]
        return [reply("1.4.2")]

    subject, _ = evaluator(script, task())

    await subject.run([task()], ["m"], retry_errors=True)

    assert [(r.attempt, r.outcome) for r in subject.finished] == [(1, "pass")]


async def test_an_internal_error_is_not_run_again() -> None:
    # Review of the audit of hito 8: a bug of maha comes back on a retry,
    # and the retry is paid.
    calls = 0

    def script(t: Task, m: str) -> list[Step]:
        nonlocal calls
        calls += 1
        raise PermissionError("cannot read the fixture")

    seen: list[TaskRun] = []
    subject, _ = evaluator(script, task())

    [run] = await subject.run([task()], ["m"], retry_errors=True, on_run=seen.append)

    assert (run.reason, calls, len(seen)) == ("internal", 1, 1)


async def test_a_check_that_crashes_keeps_what_the_run_spent() -> None:
    # Review of the audit of hito 8: the run was kept with no tokens and no
    # cost, though its calls were paid.
    broken = task(check=Check(command="pytest -q"))
    subject, _ = evaluator(says("1.4.2", tokens=100), broken, runner=FakeRunner())

    [run] = await subject.run([broken], ["m"])

    assert (run.outcome, run.reason, run.tokens) == ("error", "internal", 100)
    assert (run.detail or "").startswith("AssertionError: ")


async def test_a_run_that_breaks_mid_turn_keeps_what_it_spent() -> None:
    # Review of the audit of hito 8: as with a check that crashes.
    @asynccontextmanager
    async def open_run(t: Task, model: str, path: Path) -> AsyncIterator[Conversation]:
        world = World(MemorySessionStore(), crashing_second(), model=model)
        conversation = await world.sessions.start()
        try:
            yield conversation
        finally:
            await conversation.close()

    subject = Evaluator(
        MemoryEvalSuite([task()], FIXTURES), open_run, FakeRunner(), ENV
    )

    [run] = await subject.run([task()], ["m"])

    assert (run.outcome, run.reason, run.tokens, run.steps) == (
        "error",
        "internal",
        700,
        1,
    )
    assert run.detail == "RuntimeError: boom"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ModelRequestError("400 tools.0: invalid schema"), "request"),
        (ModelResponseError("a stream line is too long"), "response"),
    ],
)
async def test_a_broken_request_or_answer_of_maha_is_a_failure(
    error: ModelError, reason: str
) -> None:
    # Deep audit (I2): a 4xx for a request maha broke, or an answer maha
    # cannot read, left the success rate as "provider errors": a
    # regression of maha hid.
    subject, _ = evaluator(lambda t, m: [error], task())

    [run] = await subject.run([task()], ["m"], retry_errors=True)

    assert (run.outcome, run.reason) == ("fail", reason)
    assert str(error) in (run.detail or "")


@pytest.mark.parametrize(
    ("error", "reason", "retried"),
    [
        (ModelRateLimitError("429 Too Many Requests"), "provider", True),
        (ModelUnavailableError("503 Service Unavailable"), "provider", True),
        (ModelAuthError("401 Unauthorized"), "credentials", False),
    ],
)
async def test_only_what_the_provider_may_fix_is_run_again(
    error: ModelError, reason: str, retried: bool
) -> None:
    # Deep audit (I2): --retry-errors says it retries the provider's errors
    # (429, 5xx, network); a rejected key fails the same way again.
    seen: list[TaskRun] = []
    subject, _ = evaluator(lambda t, m: [error], task())

    [run] = await subject.run([task()], ["m"], retry_errors=True, on_run=seen.append)

    assert (run.outcome, run.reason) == ("error", reason)
    assert len(seen) == (2 if retried else 1)


async def test_a_test_the_agent_changed_is_put_back_and_said() -> None:
    # Deep audit (I1): the check runs the fixture's tests, not the agent's.
    fixtures = {"tienda": {"tests/test_a.py": "original\n", "src/a.py": "x\n"}}
    check = Check(command="python3 -m unittest -q tests.test_a")
    seen: list[str] = []

    class Seeing(FakeRunner):
        async def run(
            self, command: str, *, cwd: Path, time_limit: float, env: Mapping[str, str]
        ) -> CommandResult:
            seen.append((cwd / "tests/test_a.py").read_text())
            return await super().run(command, cwd=cwd, time_limit=time_limit, env=env)

    @asynccontextmanager
    async def open_run(t: Task, model: str, path: Path) -> AsyncIterator[Conversation]:
        # As an agent that rewrote the test.
        (path / "tests/test_a.py").write_text("pass\n")
        world = World(MemorySessionStore(), FakeModelClient([reply("Hecho.")]))
        conversation = await world.sessions.start()
        try:
            yield conversation
        finally:
            await conversation.close()

    ok = CommandResult(exit_code=0, output="OK", truncated=False, timed_out=False)
    suite = MemoryEvalSuite([task(check=check)], fixtures)
    subject = Evaluator(suite, open_run, Seeing([ok]), ENV)

    [run] = await subject.run([task(check=check)], ["m"])

    assert seen == ["original\n"]
    assert (run.outcome, run.restored) == ("pass", ["tests/test_a.py"])
