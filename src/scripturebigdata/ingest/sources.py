"""Source-dataset registry and a caching HTTP fetcher.

All corpora are pulled from public GitHub repositories at ingest time (never
committed), so the text stays reproducible and updatable. Downloads are cached
under ``data/cache/`` so re-runs are fast and can work offline once primed.

The fetcher is proxy-aware (honours ``HTTPS_PROXY``) and, when present, trusts
an extra CA bundle so it works behind a TLS-inspecting agent proxy.
"""

from __future__ import annotations

import hashlib
import os
import ssl
import time
import urllib.request
from pathlib import Path

# --- Edition metadata (provenance) ------------------------------------------

EDITIONS = {
    "WLC": {
        "language": "hebrew",
        "corpus": "OT",
        "title": "Westminster Leningrad Codex (OSHB morphology)",
        "source": "https://github.com/openscriptures/morphhb",
        "license": "Text: Public Domain; Morphology: CC BY 4.0",
    },
    "SBLGNT": {
        "language": "greek",
        "corpus": "NT",
        "title": "SBL Greek New Testament (MorphGNT)",
        "source": "https://github.com/morphgnt/sblgnt",
        "license": "Text: SBLGNT License; Morphology: CC BY-SA 3.0",
    },
    "LXX-Rahlfs": {
        "language": "greek",
        "corpus": "LXX",
        "title": "Septuagint (Rahlfs 1935), tagged",
        "source": "https://github.com/eliranwong/LXX-Rahlfs-1935",
        "license": "Text: Public Domain; Tagging: CC BY",
    },
}

# --- URL builders -----------------------------------------------------------

_MORPHHB = "https://raw.githubusercontent.com/openscriptures/morphhb/master/wlc/{book}.xml"

# morphhb file stems (== our OSIS ids for the OT)
MORPHHB_BOOKS = [
    "Gen", "Exod", "Lev", "Num", "Deut", "Josh", "Judg", "Ruth", "1Sam",
    "2Sam", "1Kgs", "2Kgs", "1Chr", "2Chr", "Ezra", "Neh", "Esth", "Job",
    "Ps", "Prov", "Eccl", "Song", "Isa", "Jer", "Lam", "Ezek", "Dan", "Hos",
    "Joel", "Amos", "Obad", "Jonah", "Mic", "Nah", "Hab", "Zeph", "Hag",
    "Zech", "Mal",
]

_MORPHGNT = "https://raw.githubusercontent.com/morphgnt/sblgnt/master/{file}"

# MorphGNT per-book files. The book is read from the reference inside, so the
# order here only matters for iteration.
MORPHGNT_FILES = [
    "61-Mt-morphgnt.txt", "62-Mk-morphgnt.txt", "63-Lk-morphgnt.txt",
    "64-Jn-morphgnt.txt", "65-Ac-morphgnt.txt", "66-Ro-morphgnt.txt",
    "67-1Co-morphgnt.txt", "68-2Co-morphgnt.txt", "69-Ga-morphgnt.txt",
    "70-Eph-morphgnt.txt", "71-Php-morphgnt.txt", "72-Col-morphgnt.txt",
    "73-1Th-morphgnt.txt", "74-2Th-morphgnt.txt", "75-1Ti-morphgnt.txt",
    "76-2Ti-morphgnt.txt", "77-Tit-morphgnt.txt", "78-Phm-morphgnt.txt",
    "79-Heb-morphgnt.txt", "80-Jas-morphgnt.txt", "81-1Pe-morphgnt.txt",
    "82-2Pe-morphgnt.txt", "83-1Jn-morphgnt.txt", "84-2Jn-morphgnt.txt",
    "85-3Jn-morphgnt.txt", "86-Jud-morphgnt.txt", "87-Re-morphgnt.txt",
]

_LXX_BASE = "https://raw.githubusercontent.com/eliranwong/LXX-Rahlfs-1935/master/"
LXX_FILES = {
    # global-word-index -> annotated surface (zip of a TSV of <grk> elements)
    "text": _LXX_BASE + "12-Marvel.Bible/01-text_accented.csv.zip",
    "gloss": _LXX_BASE + "12-Marvel.Bible/06-gloss.csv",
    "strongs": _LXX_BASE + "07_StrongNumber/final_Strongs.csv",
    # reference -> starting global word index
    "versification": _LXX_BASE + "08_versification/001_verse_c_modified_KEEP.csv",
}

_STRONGS = {
    "hebrew": "https://raw.githubusercontent.com/openscriptures/strongs/master/hebrew/strongs-hebrew-dictionary.js",
    "greek": "https://raw.githubusercontent.com/openscriptures/strongs/master/greek/strongs-greek-dictionary.js",
}


def morphhb_url(book: str) -> str:
    return _MORPHHB.format(book=book)


def morphgnt_url(file: str) -> str:
    return _MORPHGNT.format(file=file)


def strongs_url(language: str) -> str:
    return _STRONGS[language]


# --- Caching fetcher --------------------------------------------------------

def _cache_dir() -> Path:
    root = os.environ.get("SBD_CACHE_DIR")
    if root:
        p = Path(root)
    else:
        # data/cache relative to the repository root (two levels up from here is
        # the package; the repo root is three up). Fall back to cwd.
        here = Path(__file__).resolve()
        repo_root = here.parents[3] if len(here.parents) >= 4 else Path.cwd()
        p = repo_root / "data" / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    for candidate in (
        os.environ.get("SSL_CERT_FILE"),
        os.environ.get("REQUESTS_CA_BUNDLE"),
        "/root/.ccr/ca-bundle.crt",
    ):
        if candidate and os.path.exists(candidate):
            try:
                ctx.load_verify_locations(candidate)
            except Exception:
                pass
    return ctx


def fetch(url: str, *, use_cache: bool = True, retries: int = 4,
          timeout: int = 60) -> bytes:
    """Fetch ``url`` (proxy- and CA-aware), caching the body on disk."""
    cache = _cache_dir()
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    suffix = ".zip" if url.endswith(".zip") else ".bin"
    path = cache / (key + suffix)
    if use_cache and path.exists() and path.stat().st_size > 0:
        return path.read_bytes()

    handlers = [urllib.request.ProxyHandler(urllib.request.getproxies()),
                urllib.request.HTTPSHandler(context=_ssl_context())]
    opener = urllib.request.build_opener(*handlers)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ScriptureBigData/0.1"})
            with opener.open(req, timeout=timeout) as resp:
                data = resp.read()
            if use_cache:
                path.write_bytes(data)
            return data
        except Exception as exc:  # network hiccup -> exponential backoff
            last_err = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def fetch_text(url: str, *, encoding: str = "utf-8", **kw) -> str:
    return fetch(url, **kw).decode(encoding, errors="replace")
