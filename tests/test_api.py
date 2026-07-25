"""Smoke tests for the FastAPI web backend (skipped if FastAPI absent)."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tests.conftest import ROOT, SAMPLE  # noqa: E402


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from scripturebigdata import Scripture
    db = tmp_path_factory.mktemp("api") / "sample.sqlite"
    Scripture.from_sample(db_path=str(db), sample_dir=SAMPLE, rebuild=True).close()
    os.environ["SBD_DB"] = str(db)
    import scripturebigdata.api as api
    api._DB_PATH = str(db)  # pin the resolved path for the test
    return TestClient(api.app)


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200 and "ScriptureBigData" in r.text


def test_stats(client):
    r = client.get("/api/stats")
    assert r.status_code == 200 and r.json()["tokens"] > 3000


def test_search(client):
    r = client.get("/api/search", params={"q": "ἀγάπη", "field": "lemma"})
    assert r.status_code == 200 and r.json()["count"] >= 8


def test_xref(client):
    r = client.get("/api/xref", params={"ref": "Matt 1:23"})
    top = r.json()["results"][0]
    assert top["book"] == "Isa" and top["edition"] == "LXX-Rahlfs"


def test_lexicon(client):
    r = client.get("/api/lexicon", params={"strongs": "G26"})
    assert r.status_code == 200 and r.json()["lemma"] == "ἀγάπη"
