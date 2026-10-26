"""What every test shares."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test gets its own `XDG_DATA_HOME`: no test writes sessions, or
    anything maha keeps, into the real home (spec hito 6, §1.3)."""
    home = tmp_path / "data-home"
    monkeypatch.setenv("XDG_DATA_HOME", str(home))
    return home
