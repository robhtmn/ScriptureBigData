"""ScriptureBigData — treat Scripture as big data.

A toolkit and web application for searching, analysing, visualising and
connecting the text of the Bible in its original languages (Hebrew, Aramaic and
Greek), across the Hebrew Old Testament, the Greek New Testament and the Greek
Septuagint.

Typical usage::

    from scripturebigdata import Scripture

    bible = Scripture("scripturebigdata.sqlite")
    for hit in bible.search("ἀγάπη", field="lemma"):
        print(hit.reference, hit.text)

The heavy lifting lives in submodules:

* :mod:`scripturebigdata.canon`      — books, ordering, references
* :mod:`scripturebigdata.morphology` — decode Hebrew/Greek morphology codes
* :mod:`scripturebigdata.db`         — SQLite schema (versioned editions + variants)
* :mod:`scripturebigdata.ingest`     — download & normalise the source corpora
* :mod:`scripturebigdata.engine`     — the high-level :class:`Scripture` facade
* :mod:`scripturebigdata.analysis`   — concordance, frequency, co-occurrence, cross-refs
* :mod:`scripturebigdata.viz`        — visualisation helpers
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["Scripture", "__version__"]


def __getattr__(name: str):
    # Lazy attribute access (PEP 562): importing the package stays cheap and
    # free of import cycles; ``Scripture`` is loaded only when first used.
    if name == "Scripture":
        from .engine import Scripture
        return Scripture
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
