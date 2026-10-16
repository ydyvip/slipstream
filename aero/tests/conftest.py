"""Shared fixtures.  Drives the REAL pipeline (run_pipeline.run_pipeline) once
per session so every test asserts against the same artifacts the tool ships:
aero_normalized.csv -> aero_tables.json -> aerodynamics.xml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent          # aero/
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"

for _p in (str(ROOT), str(SCRIPTS), str(SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="session")
def pipeline():
    from run_pipeline import run_pipeline  # type: ignore[import-not-found]  # sys.path injected above

    result = run_pipeline(ROOT, generate_raw=True)
    assert not result["errors"], f"pipeline validation errors: {result['errors']}"
    return result


@pytest.fixture(scope="session")
def normalized_rows(pipeline):
    return pipeline["normalized_rows"]


@pytest.fixture(scope="session")
def tables(pipeline):
    return pipeline["tables"]


@pytest.fixture(scope="session")
def xml_text(pipeline):
    return pipeline["xml"]


@pytest.fixture(scope="session")
def configs():
    from run_pipeline import load_configs  # type: ignore[import-not-found]  # sys.path injected above

    return load_configs(ROOT)


@pytest.fixture(scope="session")
def mapping(configs):
    return configs["mapping"]


@pytest.fixture(scope="session")
def jsbsim_config(configs):
    return configs["jsbsim"]
