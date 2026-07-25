#!/usr/bin/env python3
"""Regenerate the committed offline sample under ``data/sample/``.

The sample is a curated slice of the full corpus (a few chapters from each of
the Hebrew OT, Greek NT and Septuagint) plus just the lexicon entries those
tokens reference. It lets the test-suite, the notebook and a first-run demo work
completely offline, while the full corpus is one ``sbd ingest --full`` away.

Chosen passages showcase the whole feature set — including cross-corpus links
(Matthew 1:23 quotes the Septuagint of Isaiah 7:14) and word studies (ἀγάπη).

Run:  python scripts/build_sample.py
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripturebigdata.ingest import hebrew, greek_nt, lxx, strongs   # noqa: E402
from scripturebigdata.ingest.build import build_lexicon_maps, enrich  # noqa: E402

# (book, chapter, verse_start, verse_end) — verse_end inclusive; 999 = whole chapter
SPEC = [
    ("Gen", 1, 1, 999),      # Creation
    ("Ps", 23, 1, 999),      # The LORD is my shepherd
    ("Isa", 7, 10, 17),      # Immanuel prophecy (quoted in Matthew)
    ("Isa", 53, 1, 999),     # Suffering servant
    ("Jonah", 1, 1, 999),    # Narrative sample
    ("John", 1, 1, 999),     # In the beginning was the Word
    ("Matt", 1, 1, 999),     # Genealogy + 1:23 quotes Isaiah 7:14 (LXX)
    ("Matt", 5, 1, 999),     # Sermon on the Mount / Beatitudes
    ("1John", 4, 1, 999),    # God is love (ἀγάπη word study)
]

HEBREW_BOOKS = ["Gen", "Ps", "Isa", "Jonah"]
LXX_BOOKS = ["Gen", "Isa"]     # Ps/others: LXX versification differs, skip for alignment clarity
NT_FILES = {"61-Mt-morphgnt.txt", "64-Jn-morphgnt.txt", "83-1Jn-morphgnt.txt"}


def keep(book: str, chapter: int, verse: int) -> bool:
    for b, c, v0, v1 in SPEC:
        if book == b and chapter == c and v0 <= verse <= v1:
            return True
    return False


def main() -> None:
    out = ROOT / "data" / "sample"
    out.mkdir(parents=True, exist_ok=True)

    print("Loading Strong's lexicons ...")
    lex = list(strongs.ingest())
    by_s, gk = build_lexicon_maps(lex)

    tokens = []

    def collect(stream):
        for t in stream:
            if keep(t.book, t.chapter, t.verse):
                enrich(t, by_s, gk)
                tokens.append(t)

    print("Ingesting Hebrew OT ...")
    for book in HEBREW_BOOKS:
        collect(hebrew.ingest_book(book))

    print("Ingesting Greek NT ...")
    for f in sorted(NT_FILES):
        collect(greek_nt.ingest_file(f))

    print("Ingesting Septuagint ...")
    collect(lxx.ingest(books=LXX_BOOKS))

    # Only keep lexicon entries actually referenced (keeps the sample small).
    used = {t.strongs for t in tokens if t.strongs}
    lex_used = [e for e in lex if e.strongs in used]

    tokens.sort(key=lambda t: (t.edition, t.book, t.chapter, t.verse, t.position))
    with (out / "tokens.jsonl").open("w", encoding="utf-8") as fh:
        for t in tokens:
            fh.write(json.dumps(dataclasses.asdict(t), ensure_ascii=False) + "\n")
    with (out / "lexicon.jsonl").open("w", encoding="utf-8") as fh:
        for e in lex_used:
            fh.write(json.dumps(dataclasses.asdict(e), ensure_ascii=False) + "\n")

    manifest = {
        "passages": [f"{b} {c}" + (f":{v0}-{v1}" if v1 != 999 else "") for b, c, v0, v1 in SPEC],
        "tokens": len(tokens),
        "lexicon_entries": len(lex_used),
        "editions": sorted({t.edition for t in tokens}),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(tokens)} tokens, {len(lex_used)} lexicon entries -> {out}")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
