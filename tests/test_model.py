"""Unit tests for the language-model layer (no database)."""

from __future__ import annotations

from scripturebigdata import canon, morphology
from scripturebigdata.model import strip_greek_accents, strip_hebrew_points


def test_strip_greek_accents():
    assert strip_greek_accents("ἀγάπη") == "αγαπη"
    assert strip_greek_accents("Ἰησοῦ") == "ιησου"


def test_strip_hebrew_points():
    # vowel points and cantillation removed, consonants kept
    assert strip_hebrew_points("בָּרָ֣א") == "ברא"


def test_resolve_book_aliases():
    assert canon.resolve_book("Genesis").osis == "Gen"
    assert canon.resolve_book("jn").osis == "John"
    assert canon.resolve_book("Ps").osis == "Ps"
    assert canon.resolve_book("nonsense") is None


def test_parse_reference():
    rq = canon.parse_reference("John 3:16")
    assert (rq.book, rq.chapter, rq.verse) == ("John", 3, 16)
    rq = canon.parse_reference("Ps 23:1-6")
    assert (rq.book, rq.chapter, rq.verse, rq.verse_end) == ("Ps", 23, 1, 6)
    rq = canon.parse_reference("Gen 1")
    assert (rq.book, rq.chapter, rq.verse) == ("Gen", 1, None)


def test_greek_morphgnt_decoder():
    m = morphology.parse_greek_morphgnt("V-", "3IAI-S--")
    assert m.pos == "verb"
    assert "indicative" in m.description
    m2 = morphology.parse_greek_morphgnt("N-", "----NSF-")
    assert m2.pos == "noun" and "nominative" in m2.description


def test_lxx_morph_decoder():
    m = morphology.parse_lxx_morph("V.AAI3S")
    assert m.pos == "verb"
    assert "aorist" in m.description and "3rd person" in m.description
    n = morphology.parse_lxx_morph("N.NSM")
    assert n.pos == "noun" and "masculine" in n.description


def test_hebrew_morph_decoder():
    m = morphology.parse_hebrew_morph("HVqp3ms")
    assert m.pos == "verb" and m.language == "hebrew"
    assert "qal" in m.description and "perfect" in m.description
    # prefixed article + noun
    a = morphology.parse_hebrew_morph("HTd/Ncmpa")
    assert "definite article" in a.description
