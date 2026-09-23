from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "examples" / "powertrain_demo.dbc"


@pytest.fixture
def demo_dbc_path() -> Path:
    return DBC
