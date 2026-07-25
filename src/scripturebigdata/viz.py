"""Visualisation helpers.

Two output styles:

* **Dependency-free SVG** — bar charts and a distribution strip rendered as SVG
  strings. Works everywhere (CLI, notebooks, the web app) with no third-party
  libraries, and embeds cleanly in HTML.
* **Data for interactive charts** — plain dicts/lists (nodes & links for a
  co-occurrence network, series for a distribution chart) that the web UI turns
  into interactive graphics.

An optional :func:`save_png` uses matplotlib when the ``viz`` extra is installed.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

_PALETTE = ["#4f79c7", "#e0a458", "#5aa469", "#c85c6b", "#8a6fbf", "#3fa7a0"]


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def bar_svg(items: Sequence[dict], *, value_key: str = "n",
            label_key: str = "key", sublabel_key: str | None = "gloss",
            title: str = "", width: int = 720, top: int = 20,
            color: str = _PALETTE[0]) -> str:
    """Render a horizontal bar chart as an SVG string."""
    items = list(items)[:top]
    if not items:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="40">' \
               f'<text x="8" y="24" font-family="sans-serif" font-size="13">No data</text></svg>'
    maxv = max((it.get(value_key, 0) or 0) for it in items) or 1
    row_h, pad_top, pad_left = 24, 40 if title else 12, 220
    height = pad_top + row_h * len(items) + 12
    bar_w = width - pad_left - 60
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
             f'height="{height}" font-family="sans-serif">']
    parts.append(f'<rect width="{width}" height="{height}" fill="white"/>')
    if title:
        parts.append(f'<text x="8" y="24" font-size="16" font-weight="600">'
                     f'{_esc(title)}</text>')
    for i, it in enumerate(items):
        y = pad_top + i * row_h
        v = it.get(value_key, 0) or 0
        w = max(1, int(bar_w * v / maxv))
        label = _esc(it.get(label_key, ""))
        sub = _esc(it.get(sublabel_key, "")) if sublabel_key else ""
        sub = (sub[:26] + "…") if len(sub) > 27 else sub
        parts.append(
            f'<text x="{pad_left - 8}" y="{y + 16}" text-anchor="end" '
            f'font-size="13">{label}</text>')
        parts.append(
            f'<rect x="{pad_left}" y="{y + 4}" width="{w}" height="{row_h - 10}" '
            f'rx="3" fill="{color}"/>')
        parts.append(
            f'<text x="{pad_left + w + 6}" y="{y + 16}" font-size="12" '
            f'fill="#333">{v}</text>')
        if sub:
            parts.append(
                f'<text x="{pad_left - 8}" y="{y + 16}" text-anchor="end" '
                f'font-size="13" fill="white" opacity="0"> </text>')
    parts.append('</svg>')
    return "".join(parts)


def distribution_svg(dist: Sequence[dict], *, title: str = "",
                     width: int = 760, height: int = 150) -> str:
    """Render a per-book occurrence distribution as a small column chart."""
    dist = list(dist)
    if not dist:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" ' \
               f'height="40"><text x="8" y="24" font-family="sans-serif">No data' \
               f'</text></svg>'
    maxv = max(d.get("n", 0) for d in dist) or 1
    pad_top = 36 if title else 10
    base = height - 34
    col_w = max(6, min(46, (width - 20) // max(1, len(dist))))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
             f'height="{height}" font-family="sans-serif">',
             f'<rect width="{width}" height="{height}" fill="white"/>']
    if title:
        parts.append(f'<text x="8" y="22" font-size="15" font-weight="600">'
                     f'{_esc(title)}</text>')
    for i, d in enumerate(dist):
        x = 12 + i * col_w
        h = int((base - pad_top) * d.get("n", 0) / maxv)
        y = base - h
        parts.append(f'<rect x="{x}" y="{y}" width="{col_w - 3}" height="{h}" '
                     f'rx="2" fill="{_PALETTE[0]}"><title>{_esc(d.get("book"))}: '
                     f'{d.get("n")}</title></rect>')
        parts.append(f'<text x="{x + (col_w - 3) / 2}" y="{base + 12}" '
                     f'font-size="9" text-anchor="middle" '
                     f'transform="rotate(0)">{_esc(d.get("book"))[:4]}</text>')
    parts.append('</svg>')
    return "".join(parts)


def cooccurrence_graph(center: str, cooc: Sequence[dict]) -> dict:
    """Return nodes/links describing a co-occurrence network for a web graph."""
    nodes = [{"id": center, "label": center, "central": True,
              "weight": max((c.get("n", 1) for c in cooc), default=1)}]
    links = []
    for c in cooc:
        label = c.get("lemma") or c.get("key") or c.get("strongs")
        nodes.append({"id": c.get("key") or label, "label": label,
                      "gloss": c.get("gloss", ""), "central": False,
                      "weight": c.get("n", 1)})
        links.append({"source": center, "target": c.get("key") or label,
                      "weight": c.get("n", 1)})
    return {"nodes": nodes, "links": links}


def save_png(path: str, items: Sequence[dict], *, value_key: str = "n",
             label_key: str = "key", title: str = "") -> str:
    """Save a matplotlib bar chart (requires the ``viz`` extra)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("matplotlib is required: pip install 'scripturebigdata[viz]'") from exc
    items = list(items)
    labels = [str(it.get(label_key, "")) for it in items][::-1]
    values = [it.get(value_key, 0) for it in items][::-1]
    fig, ax = plt.subplots(figsize=(9, max(2, 0.35 * len(items) + 1)))
    ax.barh(labels, values, color=_PALETTE[0])
    if title:
        ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
