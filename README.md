# ScriptureBigData

**Treat the whole of Scripture as big data** — search it, analyse it, visualise
it, find patterns in it, and connect words, phrases and passages across it, in
the **original languages**: the Hebrew/Aramaic Old Testament, the Koine Greek
New Testament, and the Greek Septuagint.

Every word is stored with its dictionary form (lemma), full grammatical parsing
(morphology), Strong's number and an English gloss. The text is modelled as
**versioned editions with a textual‑variant layer**, so it can be updated — and
new manuscript readings added — as the scholarship evolves.

```
$ sbd xref "Matt 1:23"

Passages sharing wording with Matthew 1:23 (SBLGNT)
  LXX-Rahlfs  Isaiah 7:14   (10 words) «ιδου η παρθενος εν γαστρι εξει και τεξεται υιον και»
```

That single command discovered — with no hard‑coded cross‑reference list — that
Matthew quotes the **Septuagint** of Isaiah 7:14.

---

## What it does

| Capability | How |
|---|---|
| **Search** the original text | by lemma, surface form, Strong's number, gloss, part of speech, or morphology — accent/vowel‑insensitive |
| **Phrase search** whole verses | FTS5 full‑text index over normalised Hebrew/Greek |
| **Interlinear** reading | word‑by‑word: surface · lemma · Strong's · gloss · parsing |
| **Connect languages** | align any verse across Hebrew ↔ Septuagint ↔ Greek NT |
| **Connect passages** | n‑gram cross‑reference engine finds quotations & parallels (e.g. NT quoting the LXX) |
| **Find patterns** | frequency rankings, per‑book distribution, word co‑occurrence networks |
| **Word studies** | Strong's lexicon + usage counts across all three corpora |
| **Visualise** | dependency‑free SVG charts, co‑occurrence graphs, optional matplotlib PNGs |
| **Update the text** | versioned editions + a textual‑variant / apparatus table |

Three interfaces on one engine: a **Python library**, a **`sbd` CLI**, and a
**web app**.

---

## Quick start

```bash
# From the repository root
pip install -e ".[all]"        # or ".[web]" / ".[viz]" / no extras for the core engine

# Build the small OFFLINE sample corpus (no downloads) and explore it
sbd ingest --sample
sbd stats
```

Everything below works immediately against the sample. When you're ready for the
whole Bible, run `sbd ingest --full` (downloads ~50 MB of openly‑licensed data)
and every command uses the full corpus.

### CLI

```bash
sbd search ἀγάπη --field lemma          # every form of "love"
sbd search "H430" --field strongs        # Elohim / God
sbd interlinear "John 1:1"               # word-by-word
sbd xref "Matt 1:23"                     # find the Septuagint it quotes
sbd align "Gen 1:1"                      # Hebrew next to the Greek Septuagint
sbd freq --by lemma --corpus NT --top 20 # most frequent NT words
sbd distribution "H3068" --svg name.svg  # the divine name, charted by book
sbd cooccur ἀγάπη                        # words that travel with "love"
sbd lexicon G26                          # a Strong's entry + where it occurs
sbd phrase "εν αρχη"                     # verses containing a phrase
```

### Web app

```bash
sbd serve            # http://127.0.0.1:8000
```

A single self‑contained page: word/phrase search, interlinear, cross‑references,
cross‑language alignment, frequency & distribution charts, and an interactive
co‑occurrence network — all rendered from the same JSON API.

### Python library

```python
from scripturebigdata import Scripture

bible = Scripture.from_sample()          # or Scripture("scripture.sqlite")

bible.search("ἀγάπη", field="lemma")     # -> [SearchHit, ...]
bible.interlinear("John", 1, 1)          # word-by-word data
bible.alignment("Gen", 1, 1)             # {edition: [tokens]}
bible.cross_references("SBLGNT", "Matt", 1, 23)   # finds LXX Isaiah 7:14
bible.frequency(by="lemma", corpus="NT", top=25)
bible.distribution("H3068")              # per-book counts
bible.cooccurrence("ἀγάπη")
bible.lexicon("G26")                     # Strong's entry
```

See [`notebooks/01_getting_started.ipynb`](notebooks/01_getting_started.ipynb)
for a guided tour.

---

## Updatable text & textual variants

A core requirement: *the text must be updatable as different variations are
discovered.* Two mechanisms deliver this:

1. **Versioned editions.** Every token belongs to an `edition` row recording its
   source, license and a content hash. Re‑running an ingester replaces just that
   edition, so pulling a corrected upstream text is a one‑liner:

   ```bash
   sbd ingest --full --corpora hebrew   # re-pull & rebuild only the Hebrew OT
   ```

2. **A textual‑variant apparatus.** New/alternate manuscript readings are added
   to the `variant` table *without altering the base text*:

   ```python
   bible.add_variant(
       edition="SBLGNT", book="John", chapter=1, verse=18,
       witness="Codex Sinaiticus", reading="μονογενὴς θεός",
       note="'only-begotten God' vs 'only-begotten Son'",
   )
   bible.variants("John", 1, 18)
   ```

The schema is designed so that when a new critical edition or manuscript reading
appears, you either bump an edition or attach a variant — the analysis layer
picks it up automatically.

---

## How it works

```
             download (openly-licensed sources)
  Hebrew OT ─┐   Greek NT ─┐   Septuagint ─┐   Strong's ─┐
             ▼             ▼               ▼             ▼
        ┌──────────────── ingesters ──────────────────────┐
        │  normalise every word to a single Token record  │
        │  (surface · norm · lemma · Strong's · morph ·    │
        │   gloss), enriched from the lexicon              │
        └──────────────────────┬──────────────────────────┘
                               ▼
                     SQLite (versioned editions,
                     tokens, verses, lexicon,
                     variants) + FTS5 index
                               ▼
        ┌──────────── engine: Scripture ─────────────┐
        │  search · analysis · alignment · xref · viz │
        └───────┬───────────────┬──────────────┬──────┘
              CLI            web app         notebooks
```

- **Storage.** Standard‑library `sqlite3`. The Bible is ~1M annotated tokens —
  small enough to live in one portable file, large enough that indexes and an
  FTS5 phrase index matter. No server, no heavyweight dependencies in the core.
- **Normalisation.** Hebrew is stored with points *and* a consonant‑only search
  form; Greek with accents *and* an unaccented form — so search is
  script‑faithful but forgiving.
- **Cross‑language links.** Strong's numbers tie a Greek word in the Septuagint
  to the same word in the New Testament; verse alignment ties Hebrew to its
  Greek translation; shared n‑grams tie a quotation to its source.

### Module map

| Module | Responsibility |
|---|---|
| `scripturebigdata.canon` | books, ordering, reference parsing |
| `scripturebigdata.morphology` | decode Hebrew/Greek/LXX parsing codes |
| `scripturebigdata.model` | the `Token` record + text normalisation |
| `scripturebigdata.db` | SQLite schema (editions, tokens, lexicon, variants, FTS5) |
| `scripturebigdata.ingest.*` | download & normalise each source corpus |
| `scripturebigdata.search` | word and phrase search |
| `scripturebigdata.analysis` | frequency, distribution, co‑occurrence, alignment, cross‑refs |
| `scripturebigdata.viz` | SVG / matplotlib visualisations |
| `scripturebigdata.engine` | the `Scripture` facade |
| `scripturebigdata.cli` / `.api` | CLI and web app |

---

## Building the full corpus

```bash
sbd ingest --full                     # all three corpora + lexicons
sbd ingest --full --corpora hebrew,greek_nt   # a subset
```

Downloads are cached under `data/cache/` (override with `SBD_CACHE_DIR`). The
built database lands at `data/build/scripture.sqlite`; point any command or the
web app at a specific database with `--db PATH` or the `SBD_DB` environment
variable.

Data provenance and licenses are documented in
[`DATA_SOURCES.md`](DATA_SOURCES.md). In short: Westminster Leningrad Codex with
OpenScriptures morphology (Hebrew OT), SBLGNT/MorphGNT (Greek NT), Rahlfs 1935
tagged Septuagint, and the Strong's Hebrew & Greek lexicons — all public‑domain
or Creative Commons.

---

## Development

```bash
pip install -e ".[dev]"
pytest                 # runs offline against the committed sample
python scripts/build_sample.py   # regenerate data/sample/ from live sources
```

The committed sample (`data/sample/`) covers Genesis 1, Psalm 23, Isaiah 7 & 53,
Jonah 1, John 1, Matthew 1 & 5 and 1 John 4 — enough to exercise every feature,
including the Matthew↔Septuagint quotation link.

## Roadmap

- Semantic search via multilingual embeddings (concept‑level, not just lemma)
- Syntax trees (dependency/treebank data) for structure‑aware queries
- A full critical apparatus importer (NA/BHS variants) for the variant layer
- Verse‑level English translations (WEB/BSB) as an additional reading edition

## License

Software: **MIT** (see [`LICENSE`](LICENSE)). Scripture text/data carry their own
upstream licenses — see [`DATA_SOURCES.md`](DATA_SOURCES.md).
