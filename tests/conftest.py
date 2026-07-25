"""Shared test fixtures.

The whole suite runs offline against the committed sample corpus
(``data/sample/*.jsonl``) built into a throwaway SQLite database.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SAMPLE = ROOT / "data" / "sample"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def bible(tmp_path_factory):
    from scripturebigdata import Scripture
    db = tmp_path_factory.mktemp("db") / "sample.sqlite"
    return Scripture.from_sample(db_path=str(db), sample_dir=SAMPLE, rebuild=True)
