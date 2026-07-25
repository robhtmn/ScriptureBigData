"""Ingest the Greek New Testament from MorphGNT/SBLGNT.

Each line is::

    BBCCVV  POS  PARSE  text  word  normalized  lemma

where ``BBCCVV`` encodes book (01=Matthew), chapter and verse. Strong's numbers
are not present in MorphGNT; they are attached later during the build by matching
each lemma to the Strong's Greek lexicon.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..canon import NT_NUMBER_TO_OSIS
from ..model import Token
from ..morphology import parse_greek_morphgnt
from . import sources


def parse_morphgnt(text: str, edition: str = "SBLGNT") -> Iterator[Token]:
    """Yield tokens from the contents of one MorphGNT book file."""
    cur_ref: tuple[str, int, int] | None = None
    position = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) < 7:
            continue
        bcv, pos_code, parse = parts[0], parts[1], parts[2]
        word = parts[4]           # unpunctuated surface
        lemma = parts[6]
        try:
            book_num = int(bcv[0:2]); chapter = int(bcv[2:4]); verse = int(bcv[4:6])
        except ValueError:
            continue
        book = NT_NUMBER_TO_OSIS.get(book_num)
        if not book:
            continue
        if cur_ref != (book, chapter, verse):
            cur_ref = (book, chapter, verse)
            position = 0
        position += 1
        morph = parse_greek_morphgnt(pos_code, parse)
        yield Token(
            edition=edition, language="greek",
            book=book, chapter=chapter, verse=verse, position=position,
            surface=word, lemma=lemma,
            strongs="",  # filled from lexicon during build
            morph_code=f"{pos_code} {parse}",
            morph_desc=morph.description, pos=morph.pos,
        )


def ingest_file(file: str, edition: str = "SBLGNT") -> list[Token]:
    data = sources.fetch_text(sources.morphgnt_url(file))
    return list(parse_morphgnt(data, edition=edition))


def ingest(files: list[str] | None = None, edition: str = "SBLGNT",
           progress=None) -> Iterator[Token]:
    for file in (files or sources.MORPHGNT_FILES):
        if progress:
            progress(f"Greek NT: {file}")
        try:
            yield from ingest_file(file, edition=edition)
        except Exception as exc:
            if progress:
                progress(f"  ! skipped {file}: {exc}")
