"""Search over the token/verse store.

Two complementary modes:

* **Token search** — precise, structured lookups by original-language surface
  form, lemma, Strong's number, part of speech, gloss or morphology. Uses the
  B-tree indexes; matches return one hit per word with its verse context.
* **Phrase search** — free-text phrase lookup across whole verses using the
  FTS5 index (falls back to ``LIKE`` when FTS5 is unavailable).

All original-language matching is *accent/points insensitive*: queries are
normalised the same way the stored ``norm``/``lemma_norm`` columns are.
"""

from __future__ import annotations

import sqlite3

from .canon import book_order
from .model import SearchHit, normalize_for_search


def detect_script(text: str) -> str:
    """Classify a query string as 'hebrew', 'greek' or 'latin'."""
    for ch in text:
        o = ord(ch)
        if 0x0590 <= o <= 0x05FF:
            return "hebrew"
        if (0x0370 <= o <= 0x03FF) or (0x1F00 <= o <= 0x1FFF):
            return "greek"
    return "latin"


def normalize_strongs(q: str) -> str | None:
    """Normalise a Strong's query like ``g26``/``26``/``H430`` to ``G26``."""
    q = q.strip().upper().replace(" ", "")
    if not q:
        return None
    if q[0] in ("G", "H") and q[1:].isdigit():
        return f"{q[0]}{int(q[1:])}"
    if q.isdigit():
        return q  # ambiguous language; caller may try both prefixes
    return None


_HIT_COLS = (
    "t.book, t.chapter, t.verse, t.position, t.book_order, t.surface, "
    "t.lemma, t.strongs, t.gloss, t.morph_desc, e.name AS edition, "
    "e.language, v.text AS verse_text"
)
_HIT_FROM = (
    "FROM token t JOIN edition e ON e.id = t.edition_id "
    "LEFT JOIN verse v ON v.edition_id = t.edition_id AND v.book = t.book "
    "AND v.chapter = t.chapter AND v.verse = t.verse"
)


def _row_to_hit(r: sqlite3.Row) -> SearchHit:
    return SearchHit(
        edition=r["edition"], language=r["language"], book=r["book"],
        chapter=r["chapter"], verse=r["verse"], position=r["position"],
        surface=r["surface"], lemma=r["lemma"] or "", strongs=r["strongs"] or "",
        gloss=r["gloss"] or "", morph_desc=r["morph_desc"] or "",
        verse_text=r["verse_text"] or "", book_order=r["book_order"],
    )


def _edition_filter(edition: str | None, corpus: str | None):
    clauses, params = [], []
    if edition:
        clauses.append("e.name = ?"); params.append(edition)
    if corpus:
        clauses.append("e.corpus = ?"); params.append(corpus)
    return clauses, params


def search_tokens(conn: sqlite3.Connection, query: str, *, field: str = "auto",
                  edition: str | None = None, corpus: str | None = None,
                  book: str | None = None, match: str = "exact",
                  limit: int = 200) -> list[SearchHit]:
    """Search individual words.

    ``field``: ``auto`` | ``surface`` | ``lemma`` | ``strongs`` | ``gloss`` |
    ``pos`` | ``morph``. ``match``: ``exact`` | ``prefix`` | ``contains``
    (applies to surface/lemma/gloss/morph).
    """
    query = (query or "").strip()
    if not query:
        return []

    script = detect_script(query)
    where, params = _edition_filter(edition, corpus)
    if book:
        where.append("t.book = ?"); params.append(book)

    if field == "auto":
        if normalize_strongs(query) and script == "latin" and query[0:1] in "GHgh":
            field = "strongs"
        elif script in ("hebrew", "greek"):
            field = "surface"
        else:
            field = "gloss"

    if field == "strongs":
        s = normalize_strongs(query)
        if s is None:
            return []
        if s.isdigit():
            where.append("(t.strongs = ? OR t.strongs = ?)")
            params += [f"G{s}", f"H{s}"]
        else:
            where.append("t.strongs = ?"); params.append(s)
    elif field == "pos":
        where.append("t.pos = ?"); params.append(query.lower())
    elif field == "gloss":
        where.append("t.gloss LIKE ?"); params.append(f"%{query}%")
    elif field == "morph":
        where.append("(t.morph_desc LIKE ? OR t.morph_code LIKE ?)")
        params += [f"%{query}%", f"%{query}%"]
    else:  # surface or lemma -> match normalised original-language text
        col = "t.lemma_norm" if field == "lemma" else "t.norm"
        norm = normalize_for_search(query, script if script != "latin" else "greek")
        if match == "prefix":
            where.append(f"{col} LIKE ?"); params.append(f"{norm}%")
        elif match == "contains":
            where.append(f"{col} LIKE ?"); params.append(f"%{norm}%")
        else:
            where.append(f"{col} = ?"); params.append(norm)

    sql = (f"SELECT {_HIT_COLS} {_HIT_FROM} "
           f"WHERE {' AND '.join(where)} "
           f"ORDER BY t.book_order, t.chapter, t.verse, t.position LIMIT ?")
    params.append(limit)
    return [_row_to_hit(r) for r in conn.execute(sql, params).fetchall()]


def phrase_search(conn: sqlite3.Connection, phrase: str, *,
                  edition: str | None = None, corpus: str | None = None,
                  field: str = "original", limit: int = 100) -> list[dict]:
    """Phrase search across whole verses.

    ``field``: ``original`` (Hebrew/Greek, accent-insensitive) or ``gloss``
    (English). Returns verse-level dicts.
    """
    phrase = (phrase or "").strip()
    if not phrase:
        return []
    use_fts = conn.execute(
        "SELECT value FROM meta WHERE key='fts5'").fetchone()
    use_fts = bool(use_fts and use_fts["value"] == "1")

    if field == "gloss":
        norm_phrase = phrase.lower()
        col, fts_col = "gloss", "gloss"
    else:
        script = detect_script(phrase)
        norm_phrase = normalize_for_search(phrase, script if script != "latin" else "greek")
        col, fts_col = "text_norm", "text_norm"

    where, params = [], []
    if edition:
        where.append("e.name = ?"); params.append(edition)
    if corpus:
        where.append("e.corpus = ?"); params.append(corpus)

    rows = []
    if use_fts:
        q = f'{fts_col} : "{norm_phrase}"'
        sql = ("SELECT v.book, v.chapter, v.verse, v.book_order, v.text, "
               "v.gloss, e.name AS edition, e.language "
               "FROM verse_fts f JOIN verse v ON v.id = f.rowid "
               "JOIN edition e ON e.id = v.edition_id "
               "WHERE verse_fts MATCH ?")
        params2 = [q] + params
        if where:
            sql += " AND " + " AND ".join(where)
        sql += " ORDER BY v.book_order, v.chapter, v.verse LIMIT ?"
        params2.append(limit)
        try:
            rows = conn.execute(sql, params2).fetchall()
        except sqlite3.OperationalError:
            rows = []
    if not rows:
        # LIKE fallback (also used when FTS finds nothing due to tokenisation)
        clause = list(where)
        clause.append(f"v.{col} LIKE ?")
        p = list(params) + [f"%{norm_phrase}%"]
        sql = ("SELECT v.book, v.chapter, v.verse, v.book_order, v.text, "
               "v.gloss, e.name AS edition, e.language "
               "FROM verse v JOIN edition e ON e.id = v.edition_id "
               f"WHERE {' AND '.join(clause)} "
               "ORDER BY v.book_order, v.chapter, v.verse LIMIT ?")
        p.append(limit)
        rows = conn.execute(sql, p).fetchall()

    return [
        {
            "edition": r["edition"], "language": r["language"],
            "book": r["book"], "chapter": r["chapter"], "verse": r["verse"],
            "text": r["text"], "gloss": r["gloss"],
            "reference": _fmt(r["book"], r["chapter"], r["verse"]),
        }
        for r in rows
    ]


def _fmt(book: str, chapter: int, verse: int) -> str:
    from .canon import format_reference
    return format_reference(book, chapter, verse)
