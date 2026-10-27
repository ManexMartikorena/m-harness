"""`Evaluator`: runs the battery, checks each run and keeps the provider's
failures apart (spec hito 8, §1.5 to §1.9), with fakes."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from mharness.application.evals import Evaluator, choose
from mharness.application.sessions import Conversation
from mharness.domain.commands import CommandResult
from mharness.domain.errors import ModelRateLimitError
from mharness.domain.evals import Check, Task, TaskRun
from mharness.domain.model import Usage
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
