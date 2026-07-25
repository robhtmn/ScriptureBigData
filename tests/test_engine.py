"""End-to-end tests over the sample corpus: search, analysis, connections."""

from __future__ import annotations


def test_sample_loads(bible):
    stats = bible.stats()
    assert stats["tokens"] > 3000
    names = {e["name"] for e in stats["editions"]}
    assert names == {"WLC", "SBLGNT", "LXX-Rahlfs"}


def test_search_by_lemma(bible):
    hits = bible.search("ἀγάπη", field="lemma")
    assert len(hits) >= 8
    assert all(h.strongs == "G26" for h in hits)
    assert all(h.book == "1John" for h in hits)


def test_search_by_strongs(bible):
    hits = bible.search("G2316", field="strongs")   # θεός / God
    assert hits and all(h.strongs == "G2316" for h in hits)


def test_search_by_gloss(bible):
    hits = bible.search("love", field="gloss")
    assert any(h.book == "1John" for h in hits)   # 1 John 4 — "God is love"


def test_interlinear(bible):
    toks = bible.interlinear("John", 1, 1)
    assert len(toks) == 17
    assert toks[0]["lemma"] == "ἐν"
    assert toks[1]["gloss"]  # has an English gloss


def test_frequency_nt(bible):
    rows = bible.frequency(by="lemma", corpus="NT", top=1)
    assert rows[0]["lemma"] == "ὁ"          # the article is most frequent


def test_distribution(bible):
    dist = bible.distribution("H3068")       # YHWH, the divine name
    books = {d["book"] for d in dist}
    assert "Jonah" in books and "Isa" in books


def test_cross_reference_nt_quotes_lxx(bible):
    """Matthew 1:23 should surface the Septuagint of Isaiah 7:14."""
    xrefs = bible.cross_references("SBLGNT", "Matt", 1, 23, min_n=4)
    top = xrefs[0]
    assert top["edition"] == "LXX-Rahlfs"
    assert top["book"] == "Isa" and top["chapter"] == 7 and top["verse"] == 14
    assert top["words"] >= 8


def test_alignment_hebrew_greek(bible):
    al = bible.alignment("Gen", 1, 1)
    assert set(al.keys()) == {"WLC", "LXX-Rahlfs"}
    assert al["LXX-Rahlfs"][0]["surface"] == "ἐν"


def test_cooccurrence(bible):
    rows = bible.cooccurrence("ἀγάπη", min_count=2)
    assert rows and all("n" in r for r in rows)


def test_lexicon(bible):
    e = bible.lexicon("G26")
    assert e["lemma"] == "ἀγάπη"
    assert "love" in e["gloss"].lower()


def test_phrase_search(bible):
    rows = bible.phrase("εν αρχη")
    refs = {r["reference"] for r in rows}
    assert "John 1:1" in refs


def test_variant_roundtrip(bible):
    """The updatable-text layer: register and read back a manuscript variant."""
    vid = bible.add_variant(
        edition="SBLGNT", book="John", chapter=1, verse=18, position=None,
        witness="Codex Sinaiticus", reading="μονογενὴς θεός",
        note="anarthrous; cf. 'only-begotten God' vs 'Son'",
    )
    assert vid > 0
    variants = bible.variants("John", 1, 18)
    assert any(v["witness"] == "Codex Sinaiticus" for v in variants)
