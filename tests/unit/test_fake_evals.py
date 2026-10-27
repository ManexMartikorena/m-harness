"""`MemoryEvalSuite` keeps the contract of `EvalSuite`."""

from datetime import date

from mharness.domain.evals import Baseline, Check, Task, stats
from mharness.ports.evals import EvalSuite
from tests.fakes.evals import MemoryEvalSuite
from tests.unit.test_evals import run

TASK = Task(id="01", instruction="x", fixture="tienda", check=Check(command="true"))


def baseline(day: int, model: str = "glm-5.3-flash") -> Baseline:
    tasks = {"01": stats([run()])}
    return Baseline(
        date=date(2026, 10, day),
        maha="0.7.1",
        commit=None,
        provider="opencode-go",
        model=model,
        repeat=1,
        tasks=tasks,
        total=tasks["01"],
    )


def test_satisfies_the_port() -> None:
    # mypy checks this assignment against the Protocol.
    suite: EvalSuite = MemoryEvalSuite([TASK])

    assert suite is not None


async def test_each_run_gets_its_own_copy_that_goes_away() -> None:
    suite = MemoryEvalSuite([TASK], {"tienda": {"src/a.py": "x = 1\n"}})

    async with suite.workspace(TASK) as one, suite.workspace(TASK) as other:
        assert one != other
        assert await suite.read(one, "src/a.py") == "x = 1\n"
        assert await suite.read(one, "missing.txt") is None

    assert not one.exists()


async def test_the_latest_baseline_of_the_model() -> None:
    suite = MemoryEvalSuite(
        [TASK], baselines=[baseline(20), baseline(27), baseline(28, "kimi")]
    )

    found = await suite.baseline("opencode-go", "glm-5.3-flash")

    assert found is not None
    assert found.date == date(2026, 10, 27)
    assert await suite.baseline("opencode-go", "otro") is None
