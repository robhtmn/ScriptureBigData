"""FastAPI web backend exposing the engine as a JSON API, and serving the
single-page web app.

Run with::

    sbd serve                       # or
    uvicorn scripturebigdata.api:app --reload

Database selection (in order): ``$SBD_DB`` → a built ``data/build/scripture.sqlite``
→ the committed offline sample (built on first use).
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

try:
    from fastapi import FastAPI, Query
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "The web app needs FastAPI: pip install 'scripturebigdata[web]'") from exc

from .canon import parse_reference
from .engine import Scripture, _repo_root

app = FastAPI(title="ScriptureBigData", version="0.1.0")

_WEB_DIR = Path(__file__).resolve().parent / "web"
_DB_PATH: str | None = None


def _resolve_db_path() -> str:
    global _DB_PATH
    if _DB_PATH:
        return _DB_PATH
    env = os.environ.get("SBD_DB")
    full = _repo_root() / "data" / "build" / "scripture.sqlite"
    if env:
        _DB_PATH = env
    elif full.exists() and full.stat().st_size > 0:
        _DB_PATH = str(full)
    else:
        # Build the offline sample once and use it.
        s = Scripture.from_sample()
        _DB_PATH = s.db_path
        s.close()
    return _DB_PATH


def bible() -> Scripture:
    return Scripture(_resolve_db_path())


def _hit(h) -> dict:
    d = dataclasses.asdict(h)
    d["reference"] = h.reference
    return d


def _ref(reference: str):
    rq = parse_reference(reference)
    if not rq:
        return None
    return rq


# --------------------------------------------------------------------------- #
# Frontend                                                                    #
# --------------------------------------------------------------------------- #

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    path = _WEB_DIR / "index.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "<h1>ScriptureBigData</h1><p>Frontend not found.</p>"


@app.get("/interlinear", response_class=HTMLResponse)
def interlinear_viewer() -> str:
    """NBSB interlinear workbook viewer (reads the .xlsx files in the browser)."""
    return (_WEB_DIR / "interlinear.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# API                                                                         #
# --------------------------------------------------------------------------- #

@app.get("/api/stats")
def api_stats():
    with bible() as s:
        return s.stats()


@app.get("/api/editions")
def api_editions():
    with bible() as s:
        return s.editions()


@app.get("/api/search")
def api_search(q: str, field: str = "auto", edition: str | None = None,
               corpus: str | None = None, match: str = "exact",
               limit: int = Query(100, le=1000)):
    with bible() as s:
        hits = s.search(q, field=field, edition=edition, corpus=corpus,
                        match=match, limit=limit)
        return {"query": q, "field": field, "count": len(hits),
                "results": [_hit(h) for h in hits]}


@app.get("/api/phrase")
def api_phrase(q: str, field: str = "original", edition: str | None = None,
               corpus: str | None = None, limit: int = Query(100, le=1000)):
    with bible() as s:
        rows = s.phrase(q, field=field, edition=edition, corpus=corpus, limit=limit)
        return {"query": q, "count": len(rows), "results": rows}


@app.get("/api/read")
def api_read(ref: str, edition: str | None = None):
    with bible() as s:
        return {"reference": ref, "verses": s.read(ref, edition=edition)}


@app.get("/api/interlinear")
def api_interlinear(ref: str, edition: str | None = None):
    rq = _ref(ref)
    if not rq or rq.verse is None:
        return JSONResponse({"error": "give a single verse, e.g. 'John 1:1'"}, 400)
    with bible() as s:
        return {"reference": rq.label(),
                "tokens": s.interlinear(rq.book, rq.chapter, rq.verse, edition=edition)}


@app.get("/api/concordance")
def api_concordance(word: str, by: str = "auto", edition: str | None = None,
                    limit: int = Query(300, le=2000)):
    with bible() as s:
        return {"word": word, "results": s.concordance(word, by=by, edition=edition, limit=limit)}


@app.get("/api/frequency")
def api_frequency(by: str = "lemma", corpus: str | None = None,
                  edition: str | None = None, pos: str | None = None,
                  top: int = Query(30, le=500)):
    with bible() as s:
        return {"by": by, "results": s.frequency(by=by, corpus=corpus,
                edition=edition, pos=pos, top=top)}


@app.get("/api/distribution")
def api_distribution(word: str, by: str = "auto", edition: str | None = None):
    with bible() as s:
        return {"word": word, "distribution": s.distribution(word, by=by, edition=edition)}


@app.get("/api/cooccurrence")
def api_cooccurrence(word: str, by: str = "auto", edition: str | None = None,
                     top: int = Query(25, le=200), min_count: int = 2):
    from . import viz
    with bible() as s:
        cooc = s.cooccurrence(word, by=by, edition=edition, top=top, min_count=min_count)
        return {"word": word, "results": cooc,
                "graph": viz.cooccurrence_graph(word, cooc)}


@app.get("/api/xref")
def api_xref(ref: str, edition: str | None = None, min_words: int = 3,
             limit: int = Query(25, le=200)):
    rq = _ref(ref)
    if not rq or rq.verse is None:
        return JSONResponse({"error": "give a single verse, e.g. 'Matt 1:23'"}, 400)
    with bible() as s:
        ed = edition or s._default_edition(rq.book)
        return {"reference": rq.label(), "edition": ed,
                "results": s.cross_references(ed, rq.book, rq.chapter, rq.verse,
                                              min_n=min_words, limit=limit)}


@app.get("/api/align")
def api_align(ref: str):
    rq = _ref(ref)
    if not rq or rq.verse is None:
        return JSONResponse({"error": "give a single verse, e.g. 'Gen 1:1'"}, 400)
    with bible() as s:
        return {"reference": rq.label(),
                "editions": s.alignment(rq.book, rq.chapter, rq.verse)}


@app.get("/api/lexicon")
def api_lexicon(strongs: str):
    with bible() as s:
        entry = s.lexicon(strongs)
        if not entry:
            return JSONResponse({"error": "not found"}, 404)
        entry["usage"] = s.strongs_across_corpora(strongs)
        return entry
