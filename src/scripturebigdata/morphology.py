"""Decode the morphology (grammatical parsing) codes used by the source corpora.

Three schemes are supported:

* **Greek New Testament** — MorphGNT: a 2-char part-of-speech tag plus an
  8-position parse string ``person tense voice mood case number gender degree``.
* **Greek Septuagint** — a compact ``POS.FEATURES`` code (e.g. ``V.AAI3S``,
  ``N.NSM``, ``RA.DSF``).
* **Hebrew/Aramaic Old Testament** — the OpenScriptures Hebrew Bible (OSHB)
  scheme: a language letter (``H``/``A``) followed by ``/``-separated morpheme
  codes such as ``HR/Ncfsa``.

Every decoder returns a :class:`Morph` with a normalised coarse
:attr:`Morph.pos` (``noun``/``verb``/``adjective``/…) usable for filtering, a
structured ``features`` dict, and a human-readable :attr:`Morph.description`.
The raw code is always preserved so nothing is lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Morph:
    raw: str
    pos: str = "unknown"            # coarse, normalised part of speech
    language: str = ""              # "hebrew" | "aramaic" | "greek"
    features: dict[str, str] = field(default_factory=dict)
    description: str = ""

    def __str__(self) -> str:
        return self.description or self.raw


# --------------------------------------------------------------------------- #
# Greek                                                                        #
# --------------------------------------------------------------------------- #

_GK_POS = {
    "N-": "noun", "V-": "verb", "A-": "adjective", "RA": "article",
    "RD": "pronoun", "RP": "pronoun", "RR": "pronoun", "RI": "pronoun",
    "C-": "conjunction", "D-": "adverb", "P-": "preposition",
    "X-": "particle", "I-": "interjection", "M-": "indeclinable-number",
    # Septuagint bare codes
    "N": "noun", "V": "verb", "A": "adjective", "C": "conjunction",
    "D": "adverb", "P": "preposition", "X": "particle", "I": "interjection",
    "RA_": "article", "M": "indeclinable-number",
}

_GK_PERSON = {"1": "1st person", "2": "2nd person", "3": "3rd person"}
_GK_TENSE = {
    "P": "present", "I": "imperfect", "F": "future", "A": "aorist",
    "X": "perfect", "Y": "pluperfect", "R": "perfect",
}
_GK_VOICE = {"A": "active", "M": "middle", "P": "passive"}
_GK_MOOD = {
    "I": "indicative", "D": "imperative", "S": "subjunctive",
    "O": "optative", "N": "infinitive", "P": "participle",
}
_GK_CASE = {"N": "nominative", "G": "genitive", "D": "dative",
            "A": "accusative", "V": "vocative"}
_GK_NUMBER = {"S": "singular", "P": "plural", "D": "dual"}
_GK_GENDER = {"M": "masculine", "F": "feminine", "N": "neuter"}
_GK_DEGREE = {"C": "comparative", "S": "superlative"}


def _greek_features_from_flags(
    person="", tense="", voice="", mood="", case="", number="", gender="", degree=""
) -> tuple[dict, list[str]]:
    feats: dict[str, str] = {}
    words: list[str] = []

    def add(key, table, val):
        if val and val != "-":
            name = table.get(val, val)
            feats[key] = name
            words.append(name)

    add("person", _GK_PERSON, person)
    add("tense", _GK_TENSE, tense)
    add("voice", _GK_VOICE, voice)
    add("mood", _GK_MOOD, mood)
    add("case", _GK_CASE, case)
    add("number", _GK_NUMBER, number)
    add("gender", _GK_GENDER, gender)
    add("degree", _GK_DEGREE, degree)
    return feats, words


def parse_greek_morphgnt(pos: str, parse: str) -> Morph:
    """Decode a MorphGNT ``(pos, parse)`` pair.

    ``pos`` is 2 chars (e.g. ``N-``); ``parse`` is 8 chars:
    ``person tense voice mood case number gender degree`` (``-`` = n/a).
    """
    raw = f"{pos} {parse}".strip()
    coarse = _GK_POS.get(pos, _GK_POS.get(pos.rstrip("-"), "unknown"))
    p = (parse + "--------")[:8]
    feats, words = _greek_features_from_flags(
        person=p[0], tense=p[1], voice=p[2], mood=p[3],
        case=p[4], number=p[5], gender=p[6], degree=p[7],
    )
    desc = " ".join([coarse] + words)
    return Morph(raw=raw, pos=coarse, language="greek", features=feats, description=desc)


def parse_lxx_morph(code: str) -> Morph:
    """Decode a Septuagint compact morph code, e.g. ``V.AAI3S`` or ``N.NSM``.

    Nominal codes carry ``case number gender``; verbal codes carry
    ``tense voice mood person number``.
    """
    raw = code or ""
    parts = raw.split(".")
    pos_code = parts[0] if parts else ""
    feat = parts[1] if len(parts) > 1 else ""
    coarse = _GK_POS.get(pos_code, _GK_POS.get(pos_code + "-", "unknown"))

    feats: dict[str, str] = {}
    words: list[str] = []

    if pos_code == "V":
        # tense voice mood [person number] e.g. AAI3S, AMPAPM, AAPNSM
        f = feat
        if len(f) >= 3:
            d, w = _greek_features_from_flags(tense=f[0], voice=f[1], mood=f[2])
            feats.update(d); words += w
            rest = f[3:]
            # Finite verbs end with person+number; participles/infinitives end
            # with (case) number gender.
            if rest[:1] in _GK_PERSON:
                d, w = _greek_features_from_flags(
                    person=rest[0], number=rest[1] if len(rest) > 1 else "")
                feats.update(d); words += w
            elif len(rest) == 3:
                d, w = _greek_features_from_flags(
                    case=rest[0], number=rest[1], gender=rest[2])
                feats.update(d); words += w
            elif len(rest) == 2:
                d, w = _greek_features_from_flags(number=rest[0], gender=rest[1])
                feats.update(d); words += w
    else:
        # Nominal: case number gender (e.g. NSM, DSF, GPN)
        f = feat
        if len(f) >= 3:
            feats, words = _greek_features_from_flags(
                case=f[0], number=f[1], gender=f[2])
        elif len(f) == 2:
            feats, words = _greek_features_from_flags(number=f[0], gender=f[1])

    desc = " ".join([coarse] + words)
    return Morph(raw=raw, pos=coarse, language="greek", features=feats, description=desc)


# --------------------------------------------------------------------------- #
# Hebrew / Aramaic (OSHB)                                                      #
# --------------------------------------------------------------------------- #

_HB_POS = {
    "A": "adjective", "C": "conjunction", "D": "adverb", "N": "noun",
    "P": "pronoun", "R": "preposition", "S": "suffix", "T": "particle",
    "V": "verb",
}
_HB_NOUN_TYPE = {"c": "common", "p": "proper", "g": "gentilic"}
_HB_ADJ_TYPE = {"a": "adjective", "c": "cardinal number", "g": "gentilic",
                "o": "ordinal number", "x": "adjective"}
_HB_GENDER = {"m": "masculine", "f": "feminine", "b": "both", "c": "common"}
_HB_NUMBER = {"s": "singular", "p": "plural", "d": "dual"}
_HB_STATE = {"a": "absolute", "c": "construct", "d": "determined"}
_HB_STEM = {
    "q": "qal", "N": "niphal", "p": "piel", "P": "pual", "h": "hiphil",
    "H": "hophal", "t": "hithpael", "o": "polel", "O": "polal",
    "r": "poel", "R": "poal", "m": "poel", "e": "tiphil",
    # Aramaic stems
    "a": "peal", "b": "peil", "c": "hithpeel", "d": "pael", "f": "haphel",
    "g": "hophal", "i": "hithpaal", "j": "hishtaphel",
}
_HB_ASPECT = {
    "p": "perfect", "q": "sequential perfect", "i": "imperfect",
    "w": "sequential imperfect", "h": "cohortative", "j": "jussive",
    "v": "imperative", "r": "participle active", "s": "participle passive",
    "a": "infinitive absolute", "c": "infinitive construct",
}
_HB_PARTICLE = {
    "a": "affirmation", "d": "definite article", "e": "exhortation",
    "i": "interrogative", "j": "interjection", "m": "demonstrative",
    "n": "negative", "o": "direct object marker", "r": "relative",
}
_HB_PRONOUN = {"d": "demonstrative", "f": "indefinite", "i": "interrogative",
               "p": "personal", "r": "relative"}


def _decode_hebrew_segment(seg: str) -> tuple[str, list[str]]:
    """Decode one morpheme code (already stripped of the H/A prefix)."""
    if not seg:
        return "unknown", []
    pos_letter = seg[0]
    coarse = _HB_POS.get(pos_letter, "unknown")
    rest = seg[1:]
    words: list[str] = []

    def person_gender_number(s: str) -> list[str]:
        out = []
        # forms like 3ms, 3fp, 1cs
        if s and s[0] in "123":
            out.append({"1": "1st", "2": "2nd", "3": "3rd"}[s[0]] + " person")
            s = s[1:]
        for ch in s:
            if ch in _HB_GENDER:
                out.append(_HB_GENDER[ch])
            elif ch in _HB_NUMBER:
                out.append(_HB_NUMBER[ch])
        return out

    if pos_letter == "N":
        if rest[:1] in _HB_NOUN_TYPE:
            words.append(_HB_NOUN_TYPE[rest[0]]); rest = rest[1:]
        if rest[:1] in _HB_GENDER:
            words.append(_HB_GENDER[rest[0]]); rest = rest[1:]
        if rest[:1] in _HB_NUMBER:
            words.append(_HB_NUMBER[rest[0]]); rest = rest[1:]
        if rest[:1] in _HB_STATE:
            words.append(_HB_STATE[rest[0]]); rest = rest[1:]
    elif pos_letter == "V":
        if rest[:1] in _HB_STEM:
            words.append(_HB_STEM[rest[0]]); rest = rest[1:]
        if rest[:1] in _HB_ASPECT:
            words.append(_HB_ASPECT[rest[0]]); rest = rest[1:]
        words += person_gender_number(rest)
    elif pos_letter == "A":
        if rest[:1] in _HB_ADJ_TYPE:
            words.append(_HB_ADJ_TYPE[rest[0]]); rest = rest[1:]
        if rest[:1] in _HB_GENDER:
            words.append(_HB_GENDER[rest[0]]); rest = rest[1:]
        if rest[:1] in _HB_NUMBER:
            words.append(_HB_NUMBER[rest[0]]); rest = rest[1:]
        if rest[:1] in _HB_STATE:
            words.append(_HB_STATE[rest[0]]); rest = rest[1:]
    elif pos_letter == "T":
        if rest[:1] in _HB_PARTICLE:
            words.append(_HB_PARTICLE[rest[0]])
    elif pos_letter == "P":
        if rest[:1] in _HB_PRONOUN:
            words.append(_HB_PRONOUN[rest[0]]); rest = rest[1:]
        words += person_gender_number(rest)
    elif pos_letter == "S":
        words.append("pronominal")
        words += person_gender_number(rest)
    # C (conjunction), R (preposition), D (adverb): no further features
    return coarse, words


def parse_hebrew_morph(code: str) -> Morph:
    """Decode an OSHB morph code such as ``HR/Ncfsa`` or ``HVqp3ms``.

    The leading ``H`` (Hebrew) / ``A`` (Aramaic) marks the language; the rest is
    a ``/``-separated list of morpheme codes. The coarse POS reported is that of
    the *last* (head) morpheme, which is the main word; prefixes (article,
    conjunction, preposition) are described too.
    """
    raw = code or ""
    language = "hebrew"
    body = raw
    if raw[:1] in ("H", "A"):
        language = "aramaic" if raw[0] == "A" else "hebrew"
        body = raw[1:]

    segments = body.split("/") if body else []
    seg_descs: list[str] = []
    head_pos = "unknown"
    for seg in segments:
        pos, words = _decode_hebrew_segment(seg)
        head_pos = pos  # last one wins = head word
        label = pos
        if words:
            label += " (" + ", ".join(words) + ")"
        seg_descs.append(label)

    desc = " + ".join(seg_descs) if seg_descs else raw
    return Morph(raw=raw, pos=head_pos, language=language,
                 features={"segments": desc}, description=desc)


# --------------------------------------------------------------------------- #
# Dispatch                                                                     #
# --------------------------------------------------------------------------- #

def describe(scheme: str, code: str, pos: str = "") -> Morph:
    """Decode ``code`` using the named ``scheme``.

    ``scheme`` is one of ``"hebrew"``, ``"lxx"``, ``"morphgnt"``.
    For MorphGNT pass the POS tag as ``pos`` and the 8-char parse as ``code``.
    """
    if scheme == "hebrew":
        return parse_hebrew_morph(code)
    if scheme == "lxx":
        return parse_lxx_morph(code)
    if scheme == "morphgnt":
        return parse_greek_morphgnt(pos, code)
    return Morph(raw=code, description=code)
