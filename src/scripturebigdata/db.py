"""SQLite storage: versioned editions, annotated tokens, lexicon, and a textual
variant apparatus, with an FTS5 full-text index for phrase search.

Design goals
------------
* **Versioned & updatable.** Every token belongs to an ``edition`` row that
  records the source, license and a content hash. Re-ingesting an updated source
  replaces just that edition. Newly-discovered manuscript readings are added to
  the ``variant`` table without touching the base text — satisfying the "text
  can be updated as variants are discovered" requirement.
* **Fast enough to feel like big data.** ~1M tokens across the three corpora fit
  comfortably in SQLite. Word/lemma/Strong's/POS lookups use B-tree indexes;
  phrase search uses FTS5.
* **Self-contained.** Standard-library ``sqlite3`` only.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from . import canon
from .model import Token, LexEntry

SCHEMA_VERSION = 1

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- One row per (source text, version). This is what makes the text updatable.
CREATE TABLE IF NOT EXISTS edition (
    id           INTEGER PRIMARY KEY,
    name         TEXT UNIQUE NOT NULL,   -- e.g. "WLC", "SBLGNT", "LXX-Rahlfs"
    language     TEXT NOT NULL,          -- hebrew | aramaic | greek
    corpus       TEXT NOT NULL,          -- OT | NT | LXX
    title        TEXT,
    source       TEXT,                   -- upstream repo/url
    license      TEXT,
    content_hash TEXT,                   -- provenance / version marker
    created_at   TEXT DEFAULT (datetime('now'))
);

-- The atom: one annotated word.
CREATE TABLE IF NOT EXISTS token (
    id         INTEGER PRIMARY KEY,
    edition_id INTEGER NOT NULL REFERENCES edition(id) ON DELETE CASCADE,
    book       TEXT NOT NULL,
    chapter    INTEGER NOT NULL,
    verse      INTEGER NOT NULL,
    position   INTEGER NOT NULL,
    book_order INTEGER NOT NULL,
    surface    TEXT NOT NULL,
    norm       TEXT,
    lemma      TEXT,
    lemma_norm TEXT,
    strongs    TEXT,
    morph_code TEXT,
    morph_desc TEXT,
    pos        TEXT,
    gloss      TEXT,
    translit   TEXT
);

-- Denormalised verse text for display and full-text search.
CREATE TABLE IF NOT EXISTS verse (
    id         INTEGER PRIMARY KEY,
    edition_id INTEGER NOT NULL REFERENCES edition(id) ON DELETE CASCADE,
    book       TEXT NOT NULL,
    chapter    INTEGER NOT NULL,
    verse      INTEGER NOT NULL,
    book_order INTEGER NOT NULL,
    text       TEXT,
    text_norm  TEXT,
    gloss      TEXT,
    UNIQUE(edition_id, book, chapter, verse)
);

-- Strong's (and compatible) lexicon.
CREATE TABLE IF NOT EXISTS lexicon (
    strongs       TEXT PRIMARY KEY,
    lemma         TEXT,
    translit      TEXT,
    pronunciation TEXT,
    gloss         TEXT,
    definition    TEXT,
    language      TEXT
);

-- Textual apparatus: alternate manuscript readings layered over a base edition.
-- Adding rows here is how the corpus is *updated* with newly discovered variants
-- without mutating the base text.
CREATE TABLE IF NOT EXISTS variant (
    id         INTEGER PRIMARY KEY,
    edition_id INTEGER REFERENCES edition(id) ON DELETE CASCADE,
    book       TEXT NOT NULL,
    chapter    INTEGER NOT NULL,
    verse      INTEGER NOT NULL,
    position   INTEGER,                -- word position, or NULL for verse-level
    witness    TEXT,                   -- manuscript/source of the reading
    reading    TEXT,                   -- the alternate original-language text
    lemma      TEXT,
    strongs    TEXT,
    morph_code TEXT,
    note       TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_token_ref     ON token(book, chapter, verse);
CREATE INDEX IF NOT EXISTS ix_token_edition ON token(edition_id, book_order, chapter, verse, position);
CREATE INDEX IF NOT EXISTS ix_token_strongs ON token(strongs);
CREATE INDEX IF NOT EXISTS ix_token_lemma   ON token(lemma_norm);
CREATE INDEX IF NOT EXISTS ix_token_norm    ON token(norm);
CREATE INDEX IF NOT EXISTS ix_token_pos     ON token(pos);
CREATE INDEX IF NOT EXISTS ix_verse_ref     ON verse(book, chapter, verse);
CREATE INDEX IF NOT EXISTS ix_variant_ref   ON variant(book, chapter, verse);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def has_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def get_or_create_edition(
    conn: sqlite3.Connection,
    name: str,
    language: str,
    corpus: str,
    *,
    title: str = "",
    source: str = "",
    license: str = "",
    content_hash: str = "",
    replace: bool = True,
) -> int:
    """Return the edition id, creating it (or replacing its tokens) as needed.

    When ``replace`` is true and the edition already exists, its tokens and
    verses are deleted so a fresh ingest fully refreshes the text — this is the
    update path for corrected/new source versions.
    """
    row = conn.execute("SELECT id FROM edition WHERE name = ?", (name,)).fetchone()
    if row:
        eid = row["id"]
        if replace:
            conn.execute("DELETE FROM token WHERE edition_id = ?", (eid,))
            conn.execute("DELETE FROM verse WHERE edition_id = ?", (eid,))
        conn.execute(
            "UPDATE edition SET language=?, corpus=?, title=?, source=?, "
            "license=?, content_hash=? WHERE id=?",
            (language, corpus, title, source, license, content_hash, eid),
        )
        conn.commit()
        return eid
    cur = conn.execute(
        "INSERT INTO edition(name, language, corpus, title, source, license, "
        "content_hash) VALUES(?,?,?,?,?,?,?)",
        (name, language, corpus, title, source, license, content_hash),
    )
    conn.commit()
    return cur.lastrowid


def insert_tokens(conn: sqlite3.Connection, edition_id: int,
                  tokens: Iterable[Token]) -> int:
    rows = []
    for t in tokens:
        rows.append((
            edition_id, t.book, t.chapter, t.verse, t.position,
            canon.book_order(t.book), t.surface, t.norm, t.lemma, t.lemma_norm,
            t.strongs, t.morph_code, t.morph_desc, t.pos, t.gloss, t.translit,
        ))
    conn.executemany(
        "INSERT INTO token(edition_id, book, chapter, verse, position, "
        "book_order, surface, norm, lemma, lemma_norm, strongs, morph_code, "
        "morph_desc, pos, gloss, translit) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return len(rows)


def insert_lexicon(conn: sqlite3.Connection, entries: Iterable[LexEntry]) -> int:
    rows = [
        (e.strongs, e.lemma, e.translit, e.pronunciation, e.gloss,
         e.definition, e.language)
        for e in entries
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO lexicon(strongs, lemma, translit, pronunciation, "
        "gloss, definition, language) VALUES(?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return len(rows)


def add_variant(conn: sqlite3.Connection, *, edition: str, book: str,
                chapter: int, verse: int, reading: str, witness: str = "",
                position: int | None = None, lemma: str = "", strongs: str = "",
                morph_code: str = "", note: str = "") -> int:
    """Register a textual variant (alternate reading) against an edition."""
    row = conn.execute("SELECT id FROM edition WHERE name = ?", (edition,)).fetchone()
    edition_id = row["id"] if row else None
    cur = conn.execute(
        "INSERT INTO variant(edition_id, book, chapter, verse, position, witness, "
        "reading, lemma, strongs, morph_code, note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (edition_id, book, chapter, verse, position, witness, reading, lemma,
         strongs, morph_code, note),
    )
    conn.commit()
    return cur.lastrowid


def rebuild_verses(conn: sqlite3.Connection, edition_id: int | None = None) -> None:
    """Rebuild the denormalised ``verse`` table from ``token`` rows."""
    where = "WHERE edition_id = ?" if edition_id is not None else ""
    params = (edition_id,) if edition_id is not None else ()
    if edition_id is not None:
        conn.execute("DELETE FROM verse WHERE edition_id = ?", (edition_id,))
    else:
        conn.execute("DELETE FROM verse")
    conn.execute(
        f"""
        INSERT INTO verse(edition_id, book, chapter, verse, book_order, text,
                          text_norm, gloss)
        SELECT edition_id, book, chapter, verse, book_order,
               group_concat(surface, ' '),
               group_concat(norm, ' '),
               group_concat(NULLIF(gloss, ''), ' ')
        FROM (
            SELECT * FROM token {where} ORDER BY edition_id, book_order, chapter,
                                                 verse, position
        )
        GROUP BY edition_id, book, chapter, verse
        """,
        params,
    )
    conn.commit()


def build_fts(conn: sqlite3.Connection) -> bool:
    """(Re)build the FTS5 full-text index over verse text. Returns False if FTS5
    is unavailable in this SQLite build (search then falls back to LIKE)."""
    if not has_fts5(conn):
        return False
    conn.executescript(
        """
        DROP TABLE IF EXISTS verse_fts;
        CREATE VIRTUAL TABLE verse_fts USING fts5(
            text_norm, text, gloss,
            content='verse', content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        );
        INSERT INTO verse_fts(rowid, text_norm, text, gloss)
            SELECT id, text_norm, text, gloss FROM verse;
        """
    )
    conn.commit()
    return True


def finalize(conn: sqlite3.Connection) -> dict:
    """Rebuild derived tables and indexes after ingestion; return stats."""
    rebuild_verses(conn)
    fts = build_fts(conn)
    conn.execute("ANALYZE")
    stats = corpus_stats(conn)
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('fts5', ?)",
        ("1" if fts else "0",),
    )
    conn.commit()
    return stats


def corpus_stats(conn: sqlite3.Connection) -> dict:
    tokens = conn.execute("SELECT COUNT(*) c FROM token").fetchone()["c"]
    verses = conn.execute("SELECT COUNT(*) c FROM verse").fetchone()["c"]
    lex = conn.execute("SELECT COUNT(*) c FROM lexicon").fetchone()["c"]
    variants = conn.execute("SELECT COUNT(*) c FROM variant").fetchone()["c"]
    editions = [
        dict(r) for r in conn.execute(
            "SELECT e.name, e.language, e.corpus, e.title, "
            "(SELECT COUNT(*) FROM token t WHERE t.edition_id=e.id) tokens "
            "FROM edition e ORDER BY e.id"
        ).fetchall()
    ]
    return {
        "tokens": tokens, "verses": verses, "lexicon": lex,
        "variants": variants, "editions": editions,
    }
