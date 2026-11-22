"""A normal (non-editable) install must carry agent cards, prompts, fonts and the web files."""

import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from app.registry import Registry
from conftest import ROOT

REQUIRED = [
    "app/agents/job_analyst.json",
    "app/agents/interviewer.json",
    "app/prompts/tr/_contract.md",
    "app/prompts/en/_contract.md",
    "app/prompts/tr/cv_writer.md",
    "app/assets/fonts/DejaVuSans.ttf",
    "app/web/static/index.html",
    "app/web/static/app.js",
]


def test_wheel_contains_runtime_data(tmp_path, monkeypatch):
    setuptools = pytest.importorskip("setuptools.build_meta")
    src = tmp_path / "src"
    src.mkdir()
    shutil.copytree(ROOT / "app", src / "app", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy(ROOT / name, src / name)
    out = tmp_path / "dist"
    out.mkdir()
    monkeypatch.chdir(src)
    wheel = setuptools.build_wheel(str(out))
    with zipfile.ZipFile(out / wheel) as z:
        names = set(z.namelist())
    missing = [r for r in REQUIRED if r not in names]
    assert not missing, f"wheel is missing {missing}"


def test_registry_gives_a_clear_error_when_data_is_missing(tmp_path):
    (tmp_path / "agents").mkdir()
    with pytest.raises(FileNotFoundError, match="Kurulum eksik"):
        Registry(root=tmp_path)
