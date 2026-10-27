"""What every test shares."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test gets its own `XDG_DATA_HOME`: no test writes sessions, or
    anything maha keeps, into the real home (spec hito 6, §1.3)."""
    home = tmp_path / "data-home"
    monkeypatch.setenv("XDG_DATA_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test gets its own `XDG_CONFIG_HOME`: the real `config.toml` and
    `models.toml` of the machine never change a test (spec hito 7, §4)."""
    home = tmp_path / "config-home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test gets its own `XDG_STATE_HOME`: maha.log never goes to the
    real home (spec hito 7, §1.11)."""
    home = tmp_path / "state-home"
    monkeypatch.setenv("XDG_STATE_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def clean_log() -> Iterator[None]:
    """`main()` points the `mharness` logger at a file of its test: after
    each test it goes back to how Python leaves it, so that `caplog` sees
    the warnings of the next one."""
    yield
    logger = logging.getLogger("mharness")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)
