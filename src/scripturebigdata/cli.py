"""Command-line interface: ``sbd``.

Works out of the box against the committed offline sample; point it at a full
database you built with ``sbd ingest --full``.

Examples::

    sbd ingest --sample                 # build the offline demo database
    sbd ingest --full                   # download & build the whole corpus
    sbd search ἀγάπη --field lemma      # every occurrence of "love"
    sbd interlinear "John 1:1"          # word-by-word
    sbd xref "Matt 1:23"                # find the Septuagint passage it quotes
    sbd align "Gen 1:1"                 # Hebrew next to the Greek Septuagint
    sbd freq --by lemma --corpus NT --top 20
    sbd serve                           # launch the web app
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .canon import parse_reference
from .engine import Scripture, _repo_root

DEFAULT_DB = str(_repo_root() / "data" / "build" / "scripture.sqlite")


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr)


def resolve_scripture(args) -> Scripture:
    """Open the requested database, defaulting to the offline sample."""
    db = getattr(args, "db", None) or os.environ.get("SBD_DB")
    if db:
        return Scripture(db)
    if os.path.exists(DEFAULT_DB) and os.path.getsize(DEFAULT_DB) > 0:
        return Scripture(DEFAULT_DB)
    _progress("(no database specified; using the offline sample corpus)")
    return Scripture.from_sample()


# --------------------------------------------------------------------------- #
# Commands                                                                    #
# --------------------------------------------------------------------------- #

def cmd_ingest(args) -> int:
    db = args.db or DEFAULT_DB
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    if args.sample:
        s = Scripture.from_sample(db_path=db, rebuild=True, progress=_progress)
        stats = s.stats()
    else:
        corpora = args.corpora.split(",") if args.corpora else None
        s = Scripture.build(db, corpora=corpora, progress=_progress)
        stats = s.stats()
    print(f"\nBuilt {db}")
    _print_stats(stats)
    return 0


def cmd_stats(args) -> int:
    _print_stats(resolve_scripture(args).stats())
    return 0


def cmd_search(args) -> int:
    s = resolve_scripture(args)
    hits = s.search(args.query, field=args.field, edition=args.edition,
                    corpus=args.corpus, match=args.match, limit=args.limit)
    print(f"{len(hits)} match(es) for {args.query!r} (field={args.field})\n")
    for h in hits:
        print(f"  {h.edition:11} {h.reference:18} {h.surface}  "
              f"[{h.strongs} {h.lemma}] {h.gloss[:30]}")
        if args.context and h.verse_text:
            print(f"      {h.verse_text}")
    return 0


def cmd_phrase(args) -> int:
    s = resolve_scripture(args)
    rows = s.phrase(args.query, field=args.field, edition=args.edition,
                    corpus=args.corpus, limit=args.limit)
    print(f"{len(rows)} verse(s) containing {args.query!r}\n")
    for r in rows:
        print(f"  {r['edition']:11} {r['reference']:18} {r['text']}")
    return 0


def cmd_read(args) -> int:
    s = resolve_scripture(args)
    verses = s.read(args.reference, edition=args.edition)
    if not verses:
        print("No such reference (or edition lacks it).")
        return 1
    for v in verses:
        print(f"\n{v['reference']} ({v['edition']})")
        print(f"  {v['text']}")
        if v.get("gloss"):
            print(f"  gloss: {v['gloss']}")
    return 0


def cmd_interlinear(args) -> int:
    s = resolve_scripture(args)
    rq = parse_reference(args.reference)
    if not rq or rq.verse is None:
        print("Give a single verse, e.g. 'John 1:1'.")
        return 1
    rows = s.interlinear(rq.book, rq.chapter, rq.verse, edition=args.edition)
    print(f"{rq.label()} ({rows[0]['edition'] if rows else '?'})\n")
    for t in rows:
        print(f"  {t['position']:>2}. {t['surface']:14} {t['lemma']:12} "
              f"{t['strongs']:6} {t['gloss'][:26]:26} {t['morph_desc']}")
    return 0


def cmd_concordance(args) -> int:
    s = resolve_scripture(args)
    rows = s.concordance(args.word, by=args.by, edition=args.edition,
                         limit=args.limit)
    print(f"{len(rows)} occurrence(s) of {args.word!r}\n")
    for r in rows:
        print(f"  {r['edition']:11} {r['reference']:18} {r['surface']}  "
              f"— {r['verse_text']}")
    return 0


def cmd_freq(args) -> int:
    s = resolve_scripture(args)
    rows = s.frequency(by=args.by, edition=args.edition, corpus=args.corpus,
                       pos=args.pos, top=args.top)
    print(f"Top {len(rows)} by {args.by}"
          f"{f' in {args.corpus}' if args.corpus else ''}\n")
    for r in rows:
        label = r.get("lemma") or r.get("key")
        print(f"  {r['n']:>6}  {label:14} {r.get('strongs',''):6} "
              f"{(r.get('gloss') or '')[:34]}")
    if args.svg:
        from . import viz
        Path(args.svg).write_text(viz.bar_svg(rows, title=f"Top {args.by}"))
        print(f"\nWrote {args.svg}")
    return 0


def cmd_distribution(args) -> int:
    s = resolve_scripture(args)
    dist = s.distribution(args.word, by=args.by, edition=args.edition)
    print(f"Distribution of {args.word!r} across books\n")
    for d in dist:
        print(f"  {d['book']:6} {'#' * min(60, d['n'])} {d['n']}")
    if args.svg:
        from . import viz
        Path(args.svg).write_text(viz.distribution_svg(
            dist, title=f"{args.word}: occurrences by book"))
        print(f"\nWrote {args.svg}")
    return 0


def cmd_cooccur(args) -> int:
    s = resolve_scripture(args)
    rows = s.cooccurrence(args.word, by=args.by, edition=args.edition,
                          top=args.top, min_count=args.min_count)
    print(f"Words most often sharing a verse with {args.word!r}\n")
    for r in rows:
        print(f"  {r['n']:>4}  {r.get('lemma',''):14} {r.get('strongs',''):6} "
              f"{(r.get('gloss') or '')[:34]}")
    return 0


def cmd_xref(args) -> int:
    s = resolve_scripture(args)
    rq = parse_reference(args.reference)
    if not rq or rq.verse is None:
        print("Give a single verse, e.g. 'Matt 1:23'.")
        return 1
    edition = args.edition or s._default_edition(rq.book)
    rows = s.cross_references(edition, rq.book, rq.chapter, rq.verse,
                             min_n=args.min_words, limit=args.limit)
    print(f"Passages sharing wording with {rq.label()} ({edition})\n")
    for r in rows:
        print(f"  {r['edition']:11} {r['reference']:18} ({r['words']} words) "
              f"«{r['phrase']}»")
    if not rows:
        print("  (none found in this database)")
    return 0


def cmd_align(args) -> int:
    s = resolve_scripture(args)
    rq = parse_reference(args.reference)
    if not rq or rq.verse is None:
        print("Give a single verse, e.g. 'Gen 1:1'.")
        return 1
    al = s.alignment(rq.book, rq.chapter, rq.verse)
    if not al:
        print("No data for that verse.")
        return 1
    for ed, toks in al.items():
        print(f"\n{ed} ({toks[0]['language']}):")
        print("  " + " ".join(t["surface"] for t in toks))
    return 0


def cmd_lexicon(args) -> int:
    s = resolve_scripture(args)
    e = s.lexicon(args.strongs)
    if not e:
        print("Not found.")
        return 1
    print(f"{e['strongs']}  {e['lemma']}  ({e['translit']})")
    print(f"  gloss: {e['gloss']}")
    print(f"  {e['definition']}")
    print(f"\n  usage in this database: {s.strongs_across_corpora(e['strongs'])}")
    return 0


def cmd_serve(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print("The web app needs: pip install 'scripturebigdata[web]'")
        return 1
    if args.db:
        os.environ["SBD_DB"] = args.db
    os.environ.setdefault("SBD_ALLOW_SAMPLE", "1")
    print(f"Serving ScriptureBigData on http://{args.host}:{args.port}")
    uvicorn.run("scripturebigdata.api:app", host=args.host, port=args.port,
                reload=False)
    return 0


# --------------------------------------------------------------------------- #
# Output helpers                                                              #
# --------------------------------------------------------------------------- #

def _print_stats(stats: dict) -> None:
    print(f"  tokens:   {stats['tokens']:,}")
    print(f"  verses:   {stats['verses']:,}")
    print(f"  lexicon:  {stats['lexicon']:,}")
    print(f"  variants: {stats['variants']:,}")
    print("  editions:")
    for e in stats["editions"]:
        print(f"    - {e['name']:12} {e['language']:8} {e['corpus']:4} "
              f"{e['tokens']:>7,} tokens  {e['title']}")


# --------------------------------------------------------------------------- #
# Parser                                                                       #
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sbd", description="ScriptureBigData — search & analyse Scripture "
        "in its original languages.")
    p.add_argument("--version", action="version",
                   version=f"scripturebigdata {__version__}")
    p.add_argument("--db", help="database path (default: sample corpus)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("ingest", help="build the database")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--full", action="store_true", help="download & build all corpora")
    g.add_argument("--sample", action="store_true", help="build the offline sample")
    sp.add_argument("--corpora", help="comma list: hebrew,greek_nt,lxx")
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("stats", help="corpus statistics")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("search", help="search words")
    sp.add_argument("query")
    sp.add_argument("--field", default="auto",
                    choices=["auto", "surface", "lemma", "strongs", "gloss", "pos", "morph"])
    sp.add_argument("--match", default="exact", choices=["exact", "prefix", "contains"])
    sp.add_argument("--edition")
    sp.add_argument("--corpus", choices=["OT", "NT", "LXX"])
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--context", action="store_true", help="show verse text")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("phrase", help="phrase search across verses")
    sp.add_argument("query")
    sp.add_argument("--field", default="original", choices=["original", "gloss"])
    sp.add_argument("--edition")
    sp.add_argument("--corpus", choices=["OT", "NT", "LXX"])
    sp.add_argument("--limit", type=int, default=100)
    sp.set_defaults(func=cmd_phrase)

    sp = sub.add_parser("read", help="read a passage")
    sp.add_argument("reference")
    sp.add_argument("--edition")
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("interlinear", help="word-by-word for a verse")
    sp.add_argument("reference")
    sp.add_argument("--edition")
    sp.set_defaults(func=cmd_interlinear)

    sp = sub.add_parser("concordance", help="all occurrences of a word")
    sp.add_argument("word")
    sp.add_argument("--by", default="auto", choices=["auto", "lemma", "strongs", "surface"])
    sp.add_argument("--edition")
    sp.add_argument("--limit", type=int, default=500)
    sp.set_defaults(func=cmd_concordance)

    sp = sub.add_parser("freq", help="frequency ranking")
    sp.add_argument("--by", default="lemma", choices=["lemma", "strongs", "pos", "surface"])
    sp.add_argument("--edition")
    sp.add_argument("--corpus", choices=["OT", "NT", "LXX"])
    sp.add_argument("--pos")
    sp.add_argument("--top", type=int, default=25)
    sp.add_argument("--svg", help="write an SVG bar chart to this path")
    sp.set_defaults(func=cmd_freq)

    sp = sub.add_parser("distribution", help="per-book occurrence counts")
    sp.add_argument("word")
    sp.add_argument("--by", default="auto", choices=["auto", "lemma", "strongs", "surface"])
    sp.add_argument("--edition")
    sp.add_argument("--svg", help="write an SVG chart to this path")
    sp.set_defaults(func=cmd_distribution)

    sp = sub.add_parser("cooccur", help="words that share verses with a word")
    sp.add_argument("word")
    sp.add_argument("--by", default="auto", choices=["auto", "lemma", "strongs", "surface"])
    sp.add_argument("--edition")
    sp.add_argument("--top", type=int, default=25)
    sp.add_argument("--min-count", type=int, default=2)
    sp.set_defaults(func=cmd_cooccur)

    sp = sub.add_parser("xref", help="find passages that share wording (quotations)")
    sp.add_argument("reference")
    sp.add_argument("--edition")
    sp.add_argument("--min-words", type=int, default=3)
    sp.add_argument("--limit", type=int, default=25)
    sp.set_defaults(func=cmd_xref)

    sp = sub.add_parser("align", help="parallel editions of a verse")
    sp.add_argument("reference")
    sp.set_defaults(func=cmd_align)

    sp = sub.add_parser("lexicon", help="look up a Strong's entry")
    sp.add_argument("strongs")
    sp.set_defaults(func=cmd_lexicon)

    sp = sub.add_parser("serve", help="launch the web app")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
