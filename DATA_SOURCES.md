# Data Sources & Provenance

ScriptureBigData does **not** bundle the full biblical text in this repository.
Instead it ships ingesters that download openly-licensed, scholarly datasets and
normalize them into a single database. This keeps the repo small, keeps the
provenance transparent, and — critically — makes the text **updatable**: when a
source publishes a correction or a new manuscript reading is added, you re-run
ingestion (or add a variant) and the database is rebuilt. Nothing here is
hard-coded.

Every word stored in the database records which **edition** (source + version)
it came from, so you always know the provenance of the text you are studying.

## Corpora

| Corpus | Edition | Source | License |
|--------|---------|--------|---------|
| Hebrew/Aramaic Old Testament | Westminster Leningrad Codex (WLC) with OSHB morphology | [openscriptures/morphhb](https://github.com/openscriptures/morphhb) | Text: Public Domain. Morphology: CC BY 4.0 |
| Greek New Testament | SBL Greek New Testament (SBLGNT) with MorphGNT analysis | [morphgnt/sblgnt](https://github.com/morphgnt/sblgnt) | Text: [SBLGNT License](https://sblgnt.com/license/). Morphology: CC BY-SA 3.0 |
| Greek Old Testament (Septuagint) | Rahlfs 1935 LXX, tagged (morphology, Strong's, glosses) | [eliranwong/LXX-Rahlfs-1935](https://github.com/eliranwong/LXX-Rahlfs-1935) | Text: Public Domain (Rahlfs 1935). Tagging: CC BY (see repo) |
| Strong's Hebrew lexicon | Strong's Exhaustive Concordance (1890), JSON | [openscriptures/strongs](https://github.com/openscriptures/strongs) | Public Domain / CC BY-SA |
| Strong's Greek lexicon | Strong's Exhaustive Concordance (1890), JSON | [openscriptures/strongs](https://github.com/openscriptures/strongs) | Public Domain / CC BY-SA |

## Why these sources

- **Original languages.** Every word is stored in Hebrew, Aramaic or Greek with
  its dictionary form (lemma), full morphological parsing, and Strong's number.
- **Cross-language linking.** Strong's numbers and lemmas let you connect a
  Hebrew word to how the Septuagint translated it into Greek, and to how the
  New Testament reuses that Greek vocabulary.
- **Open & citable.** All sources are freely licensed and widely used in
  scholarship, so results are reproducible and shareable.

## Updating the text / adding variants

The data model treats text as **versioned editions** plus a **variant apparatus**:

1. To pull the latest upstream text, re-run `sbd ingest --full` (or a specific
   corpus). Each ingester records the edition name and a content hash.
2. To register a newly-discovered manuscript reading without replacing the base
   text, add a row to the `variant` table (see `docs/` and
   `scripturebigdata.db`), attaching the alternate reading, its witness
   (manuscript/source), and the token(s) it applies to. Searches and displays
   can then surface the variant alongside the base reading.

See the "Updatable text & textual variants" section of the README for details.
