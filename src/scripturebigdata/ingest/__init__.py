"""Ingestion: download openly-licensed source corpora and normalise them into
:class:`~scripturebigdata.model.Token` records for storage.

Sub-modules:

* :mod:`.sources`  — the registry of source datasets + a caching fetcher
* :mod:`.hebrew`   — Westminster Leningrad Codex (OSHB / morphhb) → tokens
* :mod:`.greek_nt` — SBLGNT / MorphGNT → tokens
* :mod:`.lxx`      — Rahlfs Septuagint (tagged) → tokens
* :mod:`.strongs`  — Strong's Hebrew & Greek lexicons → lexicon entries
* :mod:`.build`    — orchestrates a full build into a SQLite database
"""

from __future__ import annotations

from . import sources, hebrew, greek_nt, lxx, strongs, build  # noqa: F401

__all__ = ["sources", "hebrew", "greek_nt", "lxx", "strongs", "build"]
