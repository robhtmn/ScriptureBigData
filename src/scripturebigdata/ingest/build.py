"""Orchestrate a full (or partial) build of the ScriptureBigData database, and
load the committed offline sample.

The pipeline:

1. create the schema
2. load the Strong's lexicons and build lookup maps
3. stream tokens from each corpus, *enriching* every token from the lexicon
   (Hebrew/LXX gain their lemma + English gloss via the Strong's number; the
   Greek NT gains its Strong's number via its lemma)
4. finalize: rebuild verse text, the FTS index, and stats
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from .. import db as dbmod
from ..model import LexEntry, Token, normalize_for_search
from . import hebrew, greek_nt, lxx, sources, strongs


# --------------------------------------------------------------------------- #
# Lexicon enrichment                                                          #
# --------------------------------------------------------------------------- #

def build_lexicon_maps(entries: Iterable[LexEntry]):
    """Return (by_strongs, greek_lemma_to_strongs) lookup maps."""
    by_strongs: dict[str, LexEntry] = {}
    greek_lemma_to_strongs: dict[str, str] = {}
    for e in entries:
        by_strongs[e.strongs] = e
        if e.language == "greek" and e.lemma:
            key = normalize_for_search(e.lemma, "greek")
            prev = greek_lemma_to_strongs.get(key)
            # deterministic: keep the lowest Strong's number for a given lemma
            if prev is None or _num(e.strongs) < _num(prev):
                greek_lemma_to_strongs[key] = e.strongs
    return by_strongs, greek_lemma_to_strongs


def _num(strongs: str) -> int:
    try:
        return int(strongs[1:])
    except (ValueError, IndexError):
        return 10**9


def enrich(token: Token, by_strongs: dict[str, LexEntry],
           greek_lemma_to_strongs: dict[str, str]) -> Token:
    """Fill in lemma, Strong's number and gloss from the lexicon in place."""
    # Greek NT tokens have a lemma but no Strong's -> look it up.
    if not token.strongs and token.lemma and token.language == "greek":
        key = normalize_for_search(token.lemma, "greek")
        token.strongs = greek_lemma_to_strongs.get(key, "")

    entry = by_strongs.get(token.strongs) if token.strongs else None
    if entry:
        # Hebrew / LXX tokens carry no lemma -> use the lexicon headword.
        if not token.lemma and entry.lemma:
            token.lemma = entry.lemma
            token.lemma_norm = normalize_for_search(entry.lemma, token.language)
        if not token.gloss and entry.gloss:
            token.gloss = entry.gloss
        if not token.translit and entry.translit:
            token.translit = entry.translit
    if token.lemma and not token.lemma_norm:
        token.lemma_norm = normalize_for_search(token.lemma, token.language)
    return token


# --------------------------------------------------------------------------- #
# Live build                                                                  #
# --------------------------------------------------------------------------- #

_INGESTERS = {
    "hebrew": ("WLC", hebrew.ingest),
    "greek_nt": ("SBLGNT", greek_nt.ingest),
    "lxx": ("LXX-Rahlfs", lxx.ingest),
}


def build_database(db_path: str, corpora: list[str] | None = None, *,
                   hebrew_books: list[str] | None = None,
                   nt_files: list[str] | None = None,
                   lxx_books: list[str] | None = None,
                   progress=None) -> dict:
    """Build a database by downloading and normalising the live sources.

    ``corpora`` selects which of ``hebrew``, ``greek_nt``, ``lxx`` to include.
    """
    corpora = corpora or ["hebrew", "greek_nt", "lxx"]
    conn = dbmod.connect(db_path)
    dbmod.init_db(conn)

    if progress:
        progress("Loading Strong's lexicons")
    lex_entries = list(strongs.ingest(progress=progress))
    dbmod.insert_lexicon(conn, lex_entries)
    by_strongs, gk_map = build_lexicon_maps(lex_entries)

    for corpus in corpora:
        edition_name, ingest_fn = _INGESTERS[corpus]
        meta = sources.EDITIONS[edition_name]
        eid = dbmod.get_or_create_edition(
            conn, edition_name, meta["language"], meta["corpus"],
            title=meta["title"], source=meta["source"], license=meta["license"],
        )
        if corpus == "hebrew":
            stream = ingest_fn(books=hebrew_books, progress=progress)
        elif corpus == "greek_nt":
            stream = ingest_fn(files=nt_files, progress=progress)
        else:
            stream = ingest_fn(books=lxx_books, progress=progress)
        enriched = (enrich(t, by_strongs, gk_map) for t in stream)
        n = dbmod.insert_tokens(conn, eid, enriched)
        if progress:
            progress(f"  {edition_name}: {n} tokens")

    if progress:
        progress("Finalising (verses + full-text index)")
    stats = dbmod.finalize(conn)
    conn.close()
    return stats


# --------------------------------------------------------------------------- #
# Offline sample (committed JSONL)                                            #
# --------------------------------------------------------------------------- #

def load_sample(db_path: str, sample_dir: str | Path, *, progress=None) -> dict:
    """Build a database from the committed sample JSONL files (no network)."""
    sample_dir = Path(sample_dir)
    conn = dbmod.connect(db_path)
    dbmod.init_db(conn)

    lex_entries = [LexEntry(**json.loads(l)) for l in
                   _read_lines(sample_dir / "lexicon.jsonl")]
    if lex_entries:
        dbmod.insert_lexicon(conn, lex_entries)

    tokens_by_edition: dict[str, list[Token]] = {}
    for line in _read_lines(sample_dir / "tokens.jsonl"):
        rec = json.loads(line)
        tokens_by_edition.setdefault(rec["edition"], []).append(Token(**rec))

    for edition_name, tokens in tokens_by_edition.items():
        meta = sources.EDITIONS.get(edition_name, {
            "language": tokens[0].language, "corpus": "OT",
            "title": edition_name, "source": "", "license": "",
        })
        eid = dbmod.get_or_create_edition(
            conn, edition_name, meta["language"], meta["corpus"],
            title=meta["title"], source=meta.get("source", ""),
            license=meta.get("license", ""),
        )
        dbmod.insert_tokens(conn, eid, tokens)
        if progress:
            progress(f"{edition_name}: {len(tokens)} tokens")

    stats = dbmod.finalize(conn)
    conn.close()
    return stats


def _read_lines(path: Path) -> Iterator[str]:
    if not path.exists():
        return iter(())
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield line
