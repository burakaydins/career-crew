from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def example_cv() -> str:
    return (ROOT / "examples" / "cv.md").read_text(encoding="utf-8")


@pytest.fixture
def example_job_text() -> str:
    return (ROOT / "examples" / "ilan.md").read_text(encoding="utf-8")
