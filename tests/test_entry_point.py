import os
import subprocess
import sys
from importlib.metadata import entry_points, version
from pathlib import Path


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


def test_a_reader_that_leaves_ends_maha_quietly(tmp_path: Path) -> None:
    # Audit of hito 8: `maha models --all | head -c0` (and `export`,
    # `stats`…) ended with a Python traceback or "Exception ignored".
    read, write = os.pipe()
    os.close(read)
    env = {
        **os.environ,
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mharness", "models", "--all"],
            stdout=write,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            check=False,
        )
    finally:
        os.close(write)

    assert (result.returncode, result.stderr) == (1, "")


def test_a_closed_stdin_is_no_input(tmp_path: Path) -> None:
    # Audit of hito 8: with stdin closed (`maha -p <&-`), the first file
    # maha opened (maha.log) took descriptor 0 and went to the model.
    config = tmp_path / "config" / "maha"
    config.mkdir(parents=True)
    (config / "config.toml").write_text(
        'provider = "local"\nmodel = "m"\n'
        '[providers.local]\nbase_url = "http://127.0.0.1:9/v1"\n',
        encoding="utf-8",
    )
    log = tmp_path / "state" / "maha" / "maha.log"
    log.parent.mkdir(parents=True)
    log.write_text("lo que dice el registro\n", encoding="utf-8")
    env = {
        **os.environ,
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }

    result = subprocess.run(
        [sys.executable, "-m", "mharness", "-p"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        preexec_fn=lambda: os.close(0),
        timeout=30,
    )

    assert result.returncode == 2
    assert "-p needs an instruction" in result.stderr
