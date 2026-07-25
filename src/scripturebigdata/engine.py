"""The :class:`Scripture` facade — the primary entry point to the toolkit.

    from scripturebigdata import Scripture

    bible = Scripture.from_sample()          # offline demo corpus
    bible = Scripture("scripturebigdata.sqlite")   # a database you built

    bible.search("ἀγάπη", field="lemma")     # every form of "love"
    bible.interlinear("John", 1, 1)          # word-by-word
    bible.cross_references("SBLGNT", "Matt", 1, 23)   # finds LXX Isaiah 7:14
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import analysis, db as dbmod, search
from .canon import BY_OSIS, ReferenceQuery, parse_reference
from .model import SearchHit


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2] if len(here.parents) >= 3 else Path.cwd()


def _default_sample_dir() -> Path:
    return _repo_root() / "data" / "sample"


class Scripture:
    """A queryable Scripture database."""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self.conn: sqlite3.Connection = dbmod.connect(self.db_path)

    # -- construction -------------------------------------------------------
    @classmethod
    def open(cls, db_path: str) -> "Scripture":
        return cls(db_path)

    @classmethod
    def build(cls, db_path: str, corpora: list[str] | None = None,
              progress=None, **kwargs) -> "Scripture":
        """Download the live sources and build a full database, then open it."""
        from .ingest.build import build_database
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        build_database(db_path, corpora=corpora, progress=progress, **kwargs)
        return cls(db_path)

    @classmethod
    def from_sample(cls, db_path: str | None = None,
                    sample_dir: str | Path | None = None,
                    rebuild: bool = False, progress=None) -> "Scripture":
        """Build (if needed) and open the small committed offline sample."""
        from .ingest.build import load_sample
        sample_dir = Path(sample_dir) if sample_dir else _default_sample_dir()
        if db_path is None:
            db_path = str(_repo_root() / "data" / "build" / "sample.sqlite")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        if rebuild or not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
            load_sample(db_path, sample_dir, progress=progress)
        return cls(db_path)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- metadata -----------------------------------------------------------
    def stats(self) -> dict:
        return dbmod.corpus_stats(self.conn)

    def editions(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT name, language, corpus, title, source, license "
            "FROM edition ORDER BY id").fetchall()]

    def lexicon(self, strongs: str) -> dict | None:
        return analysis.lexicon_entry(self.conn, strongs)

    # -- reading ------------------------------------------------------------
    def _default_edition(self, book: str) -> str | None:
        b = BY_OSIS.get(book)
        if not b:
            return None
        if b.testament == "NT":
            for name in ("SBLGNT",):
                if self._has_edition(name):
                    return name
        for name in ("WLC", "LXX-Rahlfs", "SBLGNT"):
            if self._has_edition(name):
                return name
        return None

    def _has_edition(self, name: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM edition WHERE name=?", (name,)).fetchone() is not None

    def interlinear(self, book: str, chapter: int, verse: int,
                    edition: str | None = None) -> list[dict]:
        """Word-by-word data for a verse (surface, lemma, Strong's, gloss,
        morphology) in reading order."""
        edition = edition or self._default_edition(book)
        rows = self.conn.execute(
            "SELECT t.position, t.surface, t.translit, t.lemma, t.strongs, "
            "t.gloss, t.morph_desc, t.pos, e.name AS edition, e.language "
            "FROM token t JOIN edition e ON e.id=t.edition_id "
            "WHERE e.name=? AND t.book=? AND t.chapter=? AND t.verse=? "
            "ORDER BY t.position",
            (edition, book, chapter, verse),
        ).fetchall()
        return [dict(r) for r in rows]

    def read(self, reference: str, edition: str | None = None) -> list[dict]:
        """Return the verses of a reference range with their text and tokens."""
        rq = parse_reference(reference)
        if not rq:
            return []
        return self.passage(rq, edition=edition)

    def passage(self, rq: ReferenceQuery, edition: str | None = None) -> list[dict]:
        edition = edition or self._default_edition(rq.book)
        where = ["e.name=?", "v.book=?"]
        params: list = [edition, rq.book]
        if rq.chapter is not None:
            where.append("v.chapter=?"); params.append(rq.chapter)
        if rq.verse is not None:
            end = rq.verse_end or rq.verse
            where.append("v.verse BETWEEN ? AND ?"); params += [rq.verse, end]
        rows = self.conn.execute(
            "SELECT v.book, v.chapter, v.verse, v.text, v.gloss "
            "FROM verse v JOIN edition e ON e.id=v.edition_id "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY v.chapter, v.verse", params,
        ).fetchall()
        out = []
        from .canon import format_reference
        for r in rows:
            out.append({
                "reference": format_reference(r["book"], r["chapter"], r["verse"]),
                "book": r["book"], "chapter": r["chapter"], "verse": r["verse"],
                "edition": edition, "text": r["text"], "gloss": r["gloss"],
            })
        return out

    # -- search -------------------------------------------------------------
    def search(self, query: str, **kwargs) -> list[SearchHit]:
        return search.search_tokens(self.conn, query, **kwargs)

    def phrase(self, phrase: str, **kwargs) -> list[dict]:
        return search.phrase_search(self.conn, phrase, **kwargs)

    # -- analysis -----------------------------------------------------------
    def concordance(self, key: str, **kwargs) -> list[dict]:
        return analysis.concordance(self.conn, key, **kwargs)

    def frequency(self, **kwargs) -> list[dict]:
        return analysis.frequency(self.conn, **kwargs)

    def distribution(self, key: str, **kwargs) -> list[dict]:
        return analysis.distribution(self.conn, key, **kwargs)

    def cooccurrence(self, key: str, **kwargs) -> list[dict]:
        return analysis.cooccurrence(self.conn, key, **kwargs)

    def strongs_across_corpora(self, strongs: str) -> list[dict]:
        return analysis.strongs_across_corpora(self.conn, strongs)

    def alignment(self, book: str, chapter: int, verse: int,
                  editions: list[str] | None = None) -> dict:
        return analysis.alignment(self.conn, book, chapter, verse, editions)

    def cross_references(self, edition: str, book: str, chapter: int,
                         verse: int, **kwargs) -> list[dict]:
        return analysis.cross_references(self.conn, edition, book, chapter,
                                         verse, **kwargs)

    # -- variants (updatable text) -----------------------------------------
    def add_variant(self, **kwargs) -> int:
        """Register a textual variant (alternate manuscript reading)."""
        return dbmod.add_variant(self.conn, **kwargs)

    def variants(self, book: str, chapter: int, verse: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM variant WHERE book=? AND chapter=? AND verse=? "
            "ORDER BY position", (book, chapter, verse)).fetchall()
        return [dict(r) for r in rows]
