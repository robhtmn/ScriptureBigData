"""Corpus analytics: frequency, distribution, co-occurrence, cross-language
alignment, and cross-reference / quotation detection.

These are the "find patterns" and "connect words and passages" capabilities.
Everything is expressed as SQL over the token/verse store so it stays fast on
the full ~1M-token corpus.
"""

from __future__ import annotations

import sqlite3

from .canon import format_reference
from .model import normalize_for_search
from .search import detect_script, normalize_strongs


# --------------------------------------------------------------------------- #
# Frequency & distribution                                                    #
# --------------------------------------------------------------------------- #

def frequency(conn: sqlite3.Connection, *, by: str = "lemma",
              edition: str | None = None, corpus: str | None = None,
              pos: str | None = None, top: int = 50,
              min_count: int = 1) -> list[dict]:
    """Most frequent lemmas / Strong's numbers / parts of speech."""
    col = {"lemma": "t.lemma_norm", "strongs": "t.strongs",
           "pos": "t.pos", "surface": "t.norm"}[by]
    where = [f"{col} != ''"]
    params: list = []
    if edition:
        where.append("e.name = ?"); params.append(edition)
    if corpus:
        where.append("e.corpus = ?"); params.append(corpus)
    if pos:
        where.append("t.pos = ?"); params.append(pos)
    sql = (
        f"SELECT {col} AS key, COUNT(*) AS n, "
        "MIN(t.lemma) AS lemma, MIN(t.strongs) AS strongs, "
        "MIN(t.gloss) AS gloss "
        "FROM token t JOIN edition e ON e.id = t.edition_id "
        f"WHERE {' AND '.join(where)} "
        f"GROUP BY {col} HAVING n >= ? ORDER BY n DESC LIMIT ?"
    )
    params += [min_count, top]
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def distribution(conn: sqlite3.Connection, key: str, *, by: str = "auto",
                 edition: str | None = None) -> list[dict]:
    """Per-book occurrence counts for a lemma or Strong's number — the data
    behind an "occurrences across Scripture" chart."""
    field, value = _resolve_key(key, by)
    where = [f"t.{field} = ?"]
    params: list = [value]
    if edition:
        where.append("e.name = ?"); params.append(edition)
    sql = (
        "SELECT t.book AS book, MIN(t.book_order) AS book_order, "
        "COUNT(*) AS n FROM token t JOIN edition e ON e.id = t.edition_id "
        f"WHERE {' AND '.join(where)} "
        "GROUP BY t.book ORDER BY book_order"
    )
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def concordance(conn: sqlite3.Connection, key: str, *, by: str = "auto",
                edition: str | None = None, limit: int = 500) -> list[dict]:
    """Every occurrence of a word (by lemma/Strong's/surface) with verse text."""
    field, value = _resolve_key(key, by)
    where = [f"t.{field} = ?"]
    params: list = [value]
    if edition:
        where.append("e.name = ?"); params.append(edition)
    sql = (
        "SELECT e.name AS edition, t.book, t.chapter, t.verse, t.position, "
        "t.surface, t.lemma, t.strongs, t.gloss, t.morph_desc, "
        "v.text AS verse_text, t.book_order "
        "FROM token t JOIN edition e ON e.id = t.edition_id "
        "LEFT JOIN verse v ON v.edition_id=t.edition_id AND v.book=t.book "
        "AND v.chapter=t.chapter AND v.verse=t.verse "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY t.book_order, t.chapter, t.verse, t.position LIMIT ?"
    )
    params.append(limit)
    out = []
    for r in conn.execute(sql, params).fetchall():
        d = dict(r)
        d["reference"] = format_reference(r["book"], r["chapter"], r["verse"])
        out.append(d)
    return out


def cooccurrence(conn: sqlite3.Connection, key: str, *, by: str = "auto",
                 edition: str | None = None, top: int = 25,
                 min_count: int = 2) -> list[dict]:
    """Words that most often share a verse with the target word.

    Powers "which words travel together" network/graph visualisations.
    """
    field, value = _resolve_key(key, by)
    ed = "AND e.name = ?" if edition else ""
    params: list = [value]
    if edition:
        params.append(edition)
    # verses containing the target
    sql = (
        "WITH target AS ("
        "  SELECT DISTINCT t.edition_id, t.book, t.chapter, t.verse "
        "  FROM token t JOIN edition e ON e.id=t.edition_id "
        f"  WHERE t.{field} = ? {ed}"
        ") "
        "SELECT t.lemma_norm AS key, MIN(t.lemma) AS lemma, "
        "  MIN(t.strongs) AS strongs, MIN(t.gloss) AS gloss, COUNT(*) AS n "
        "FROM token t JOIN target ON target.edition_id=t.edition_id "
        "  AND target.book=t.book AND target.chapter=t.chapter "
        "  AND target.verse=t.verse "
        f"WHERE t.lemma_norm != '' AND t.{field} != ? "
        "GROUP BY t.lemma_norm HAVING n >= ? ORDER BY n DESC LIMIT ?"
    )
    params2 = ([value] + ([edition] if edition else []) + [value, min_count, top])
    return [dict(r) for r in conn.execute(sql, params2).fetchall()]


def strongs_across_corpora(conn: sqlite3.Connection, strongs: str) -> list[dict]:
    """How often a Strong's number occurs in each edition — e.g. a Greek word
    shared between the Septuagint and the New Testament."""
    s = normalize_strongs(strongs) or strongs
    sql = (
        "SELECT e.name AS edition, e.corpus, e.language, COUNT(*) AS n "
        "FROM token t JOIN edition e ON e.id=t.edition_id "
        "WHERE t.strongs = ? GROUP BY e.name ORDER BY n DESC"
    )
    return [dict(r) for r in conn.execute(sql, (s,)).fetchall()]


# --------------------------------------------------------------------------- #
# Cross-language alignment (same reference, different edition)                 #
# --------------------------------------------------------------------------- #

def alignment(conn: sqlite3.Connection, book: str, chapter: int, verse: int,
              editions: list[str] | None = None) -> dict[str, list[dict]]:
    """Return the tokens of a verse in every available edition, side by side.

    For an Old Testament verse this places the Hebrew (WLC) next to the Greek
    Septuagint (LXX-Rahlfs), letting you see how a Hebrew word was translated.
    """
    where = ["t.book = ?", "t.chapter = ?", "t.verse = ?"]
    params: list = [book, chapter, verse]
    if editions:
        where.append("e.name IN (%s)" % ",".join("?" * len(editions)))
        params += editions
    sql = (
        "SELECT e.name AS edition, e.language, t.position, t.surface, "
        "t.lemma, t.strongs, t.gloss, t.morph_desc "
        "FROM token t JOIN edition e ON e.id=t.edition_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY e.name, t.position"
    )
    out: dict[str, list[dict]] = {}
    for r in conn.execute(sql, params).fetchall():
        out.setdefault(r["edition"], []).append(dict(r))
    return out


# --------------------------------------------------------------------------- #
# Cross-references / quotation detection (shared n-grams)                      #
# --------------------------------------------------------------------------- #

def _verse_norm_tokens(conn, edition, book, chapter, verse) -> list[str]:
    row = conn.execute(
        "SELECT v.text_norm FROM verse v JOIN edition e ON e.id=v.edition_id "
        "WHERE e.name=? AND v.book=? AND v.chapter=? AND v.verse=?",
        (edition, book, chapter, verse),
    ).fetchone()
    if not row or not row["text_norm"]:
        return []
    return [w for w in row["text_norm"].split() if w]


def cross_references(conn: sqlite3.Connection, edition: str, book: str,
                     chapter: int, verse: int, *, min_n: int = 3,
                     max_n: int = 10, limit: int = 25) -> list[dict]:
    """Find other verses that share a run of words with the given verse.

    Uses the FTS phrase index to locate the *longest* shared word-sequences,
    which is exactly how a New Testament quotation of the Septuagint shows up
    (e.g. Matthew 1:23 ↔ LXX Isaiah 7:14). Cross-edition matches are quotations
    or translation parallels; same-edition matches are internal repetitions.
    """
    tokens = _verse_norm_tokens(conn, edition, book, chapter, verse)
    if len(tokens) < min_n:
        return []
    use_fts = conn.execute("SELECT value FROM meta WHERE key='fts5'").fetchone()
    use_fts = bool(use_fts and use_fts["value"] == "1")

    found: dict[tuple, dict] = {}
    upper = min(max_n, len(tokens))
    for n in range(upper, min_n - 1, -1):
        for i in range(0, len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i + n])
            for m in _match_phrase(conn, phrase, use_fts):
                if (m["edition"], m["book"], m["chapter"], m["verse"]) == \
                        (edition, book, chapter, verse):
                    continue
                k = (m["edition"], m["book"], m["chapter"], m["verse"])
                # keep the longest shared phrase per matched verse
                if k not in found or len(phrase) > len(found[k]["phrase"]):
                    found[k] = {**m, "phrase": phrase, "words": n}
        if len(found) >= limit and n < upper:
            break
    results = sorted(found.values(), key=lambda d: (-d["words"], d["book_order"],
                                                    d["chapter"], d["verse"]))
    return results[:limit]


def _match_phrase(conn, phrase: str, use_fts: bool) -> list[dict]:
    rows = []
    if use_fts:
        try:
            rows = conn.execute(
                'SELECT v.book, v.chapter, v.verse, v.book_order, v.text, '
                'e.name AS edition, e.language '
                'FROM verse_fts f JOIN verse v ON v.id=f.rowid '
                'JOIN edition e ON e.id=v.edition_id '
                'WHERE verse_fts MATCH ?',
                (f'text_norm : "{phrase}"',),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    if not rows and not use_fts:
        rows = conn.execute(
            "SELECT v.book, v.chapter, v.verse, v.book_order, v.text, "
            "e.name AS edition, e.language FROM verse v "
            "JOIN edition e ON e.id=v.edition_id WHERE v.text_norm LIKE ?",
            (f"%{phrase}%",),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["reference"] = format_reference(r["book"], r["chapter"], r["verse"])
        out.append(d)
    return out


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _resolve_key(key: str, by: str) -> tuple[str, str]:
    """Return (token_column, normalised_value) for a lemma/Strong's/surface key."""
    if by == "auto":
        if normalize_strongs(key) and key[:1] in "GHgh":
            by = "strongs"
        elif detect_script(key) in ("hebrew", "greek"):
            by = "lemma"
        else:
            by = "strongs" if key[:1].isdigit() else "lemma"
    if by == "strongs":
        return "strongs", (normalize_strongs(key) or key)
    if by == "surface":
        return "norm", normalize_for_search(key, _script_lang(key))
    return "lemma_norm", normalize_for_search(key, _script_lang(key))


def _script_lang(text: str) -> str:
    s = detect_script(text)
    return s if s in ("hebrew", "greek") else "greek"


def lexicon_entry(conn: sqlite3.Connection, strongs: str) -> dict | None:
    s = normalize_strongs(strongs) or strongs
    r = conn.execute("SELECT * FROM lexicon WHERE strongs = ?", (s,)).fetchone()
    return dict(r) if r else None
