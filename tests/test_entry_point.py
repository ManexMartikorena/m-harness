import subprocess
import sys
from importlib.metadata import entry_points, version


def test_maha_script_points_to_composition_root() -> None:
    (script,) = entry_points(group="console_scripts", name="maha")

    assert script.value == "mharness.bootstrap:main"


def test_python_m_mharness_prints_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mharness", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == f"maha {version('m-harness')}\n"
