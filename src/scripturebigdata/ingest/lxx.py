"""Ingest the Greek Septuagint (Rahlfs 1935) from eliranwong/LXX-Rahlfs-1935.

The source stores the text as several parallel files keyed by a global word
index (1..623693):

* ``text``          — ``idx <TAB> <grk ... morph="CODE">surface</grk>``
* ``gloss``         — ``idx <TAB> english;<br>alternatives``
* ``strongs``       — ``idx <TAB> G####``
* ``versification`` — ``Book.Chapter.Verse <TAB> starting-idx``

We join them on the word index and cut the stream into verses using the
versification map. The Greek *lemma* headword is filled from the Strong's Greek
lexicon during the build (via the Strong's number).
"""

from __future__ import annotations

import bisect
import io
import re
import zipfile
from collections.abc import Iterator

from ..canon import LXX_ABBREV_TO_OSIS
from ..model import Token
from ..morphology import parse_lxx_morph
from . import sources

_GRK = re.compile(r'morph="([^"]*)"[^>]*>([^<]*)</grk>')

# Extra Septuagint book-code suffixes (Theodotion / Old Greek editions).
_LXX_SUFFIX_MAP = {
    "SusTh": "Sus", "SusOG": "Sus", "BelTh": "Bel", "BelOG": "Bel",
    "DanTh": "Dan", "DanOG": "Dan", "EsthGr": "Esth", "DanGr": "Dan",
}


def _ref_to_osis(book_code: str) -> str | None:
    if book_code in LXX_ABBREV_TO_OSIS:
        return LXX_ABBREV_TO_OSIS[book_code]
    if book_code in _LXX_SUFFIX_MAP:
        return _LXX_SUFFIX_MAP[book_code]
    for suffix in ("Th", "OG", "Gr", "LXX"):
        if book_code.endswith(suffix):
            base = book_code[: -len(suffix)]
            return LXX_ABBREV_TO_OSIS.get(base, base or None)
    return LXX_ABBREV_TO_OSIS.get(book_code, book_code or None)


def _parse_versification(text: str):
    """Return (starts, refs) parallel lists sorted by starting index, where
    refs[i] = (osis, chapter, verse) begins at word index starts[i]."""
    entries = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            ref, idx = line.split("\t")
        except ValueError:
            continue
        parts = ref.split(".")
        if len(parts) < 3:
            continue
        book_code, chap, vs = parts[0], parts[1], parts[2]
        osis = _ref_to_osis(book_code)
        if not osis:
            continue
        try:
            entries.append((int(idx), osis, int(chap), int(vs)))
        except ValueError:
            continue
    entries.sort()
    starts = [e[0] for e in entries]
    refs = [(e[1], e[2], e[3]) for e in entries]
    return starts, refs


def _load_simple_map(text: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for line in text.splitlines():
        if "\t" not in line:
            continue
        key, _, val = line.partition("\t")
        try:
            out[int(key)] = val
        except ValueError:
            continue
    return out


def _clean_gloss(raw: str) -> str:
    if not raw:
        return ""
    return re.split(r";|<br>", raw)[0].strip()


def ingest(books: list[str] | None = None, edition: str = "LXX-Rahlfs",
           progress=None) -> Iterator[Token]:
    """Yield LXX tokens. If ``books`` is given, only those OSIS books are
    emitted (useful for building a small sample)."""
    if progress:
        progress("Septuagint: fetching parallel data files")
    versif = sources.fetch_text(sources.LXX_FILES["versification"])
    starts, refs = _parse_versification(versif)
    if not starts:
        return
    max_idx = None
    want = set(books) if books else None

    # Precompute which word-index ranges we care about (for sampling).
    wanted_idx: set[int] | None = None
    if want is not None:
        wanted_idx = set()
        for i, (osis, _c, _v) in enumerate(refs):
            if osis in want:
                lo = starts[i]
                hi = starts[i + 1] if i + 1 < len(starts) else lo + 200
                wanted_idx.update(range(lo, hi))
        if not wanted_idx:
            return
        max_idx = max(wanted_idx)

    gloss = _load_simple_map(sources.fetch_text(sources.LXX_FILES["gloss"]))
    strongs = _load_simple_map(sources.fetch_text(sources.LXX_FILES["strongs"]))

    if progress:
        progress("Septuagint: decoding text")
    zip_bytes = sources.fetch(sources.LXX_FILES["text"])
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    name = zf.namelist()[0]

    def ref_for(idx: int):
        pos = bisect.bisect_right(starts, idx) - 1
        if pos < 0:
            return None
        osis, chap, vs = refs[pos]
        return osis, chap, vs, starts[pos]

    with zf.open(name) as fh:
        for raw in io.TextIOWrapper(fh, encoding="utf-8", errors="replace"):
            raw = raw.rstrip("\n")
            if "\t" not in raw:
                continue
            key, _, payload = raw.partition("\t")
            try:
                idx = int(key)
            except ValueError:
                continue
            if wanted_idx is not None:
                if idx > max_idx:
                    break
                if idx not in wanted_idx:
                    continue
            m = _GRK.search(payload)
            if not m:
                continue
            morph_code, surface = m.group(1), m.group(2)
            info = ref_for(idx)
            if not info:
                continue
            osis, chap, vs, start = info
            if want is not None and osis not in want:
                continue
            morph = parse_lxx_morph(morph_code)
            yield Token(
                edition=edition, language="greek",
                book=osis, chapter=chap, verse=vs, position=idx - start + 1,
                surface=surface, lemma="",  # filled from lexicon during build
                strongs=strongs.get(idx, ""),
                morph_code=morph_code, morph_desc=morph.description, pos=morph.pos,
                gloss=_clean_gloss(gloss.get(idx, "")),
            )
