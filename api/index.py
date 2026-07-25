"""Vercel serverless entry point for the ScriptureBigData web app.

Vercel's Python runtime serves the exported FastAPI ``app`` as an ASGI function.
Vercel's filesystem is read-only except for ``/tmp``, so on cold start we build
the small committed offline sample database into ``/tmp`` — the deployment is
then fully self-contained and needs no external services or network.

For a *full*-corpus deployment, commit a prebuilt ``scripture.sqlite`` and set
the ``SBD_DB`` environment variable to its path instead.
"""

import os
import sys

# The repo root (one level up from this ``api/`` directory).
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))

# /tmp is the only writable location on Vercel.
os.environ.setdefault("SBD_DB", "/tmp/scripturebigdata.sqlite")
os.environ.setdefault("SBD_CACHE_DIR", "/tmp/sbd-cache")

from scripturebigdata.ingest.build import load_sample  # noqa: E402

_db = os.environ["SBD_DB"]
if not os.path.exists(_db) or os.path.getsize(_db) == 0:
    load_sample(_db, os.path.join(BASE, "data", "sample"))

# Vercel discovers this ``app`` (ASGI) and serves it.
from scripturebigdata.api import app  # noqa: E402,F401
