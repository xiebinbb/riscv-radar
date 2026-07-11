#!/usr/bin/env python3
"""Build a static RISC-V radar site from daily JSON data."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DAILY_DIR = ROOT / "data" / "daily"
SITE_DIR = ROOT / "site"
DIST_DIR = ROOT / "dist"
CATEGORIES = {
    "news": "News",
    "paper": "Papers",
    "startup": "Startups",
    "market": "Markets",
    "tech": "Technology",
}


def load_latest() -> dict[str, Any]:
    files = sorted(DAILY_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No daily data found. Run scripts/collect.py first.")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def fmt_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return value[:10]


def item_card(item: dict[str, Any]) -> str:
    tags = "".join(f"<span>{escape(tag)}</span>" for tag in item.get("tags", [])[:5])
    entities = ", ".join(escape(entity) for entity in item.get("entities", [])[:4])
    entity_html = f"<p class=\"entities\">{entities}</p>" if entities else ""
    summary = escape(item.get("summary") or "No summary available.")
    return f"""
      <article class="item-card">
        <div class="item-meta">
          <span>{escape(CATEGORIES.get(item['category'], item['category'].title()))}</span>
          <span>{escape(item['source'])}</span>
          <span>{fmt_date(item['published_at'])}</span>
        </div>
        <h3><a href="{escape(item['url'])}" rel="noopener noreferrer" target="_blank">{escape(item['title'])}</a></h3>
        <p>{summary}</p>
        {entity_html}
        <div class="tag-row">{tags}</div>
      </article>
    """


def group_by_category(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        groups[item["category"]].append(item)
    return groups


def render_index(data: dict[str, Any]) -> str:
    items = data["items"]
    groups = group_by_category(items)
    top = items[:8]
    category_nav = "".join(
        f"<a href=\"#{key}\">{label}<strong>{len(groups.get(key, []))}</strong></a>"
        for key, label in CATEGORIES.items()
    )
    top_cards = "\n".join(item_card(item) for item in top)
    sections = []
    for key, label in CATEGORIES.items():
        section_items = groups.get(key, [])[:12]
        if not section_items:
            continue
        sections.append(
            f"""
            <section id="{key}" class="category-section">
              <div class="section-heading">
                <h2>{label}</h2>
                <span>{len(groups.get(key, []))} items</span>
              </div>
              <div class="item-grid">
                {''.join(item_card(item) for item in section_items)}
              </div>
            </section>
            """
        )
    errors = data.get("errors", [])
    error_html = ""
    if errors:
        rows = "".join(f"<li>{escape(row['source'])}: {escape(row['error'])}</li>" for row in errors)
        error_html = f"<details class=\"errors\"><summary>Source warnings</summary><ul>{rows}</ul></details>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RISC-V Radar</title>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
  <header class="site-header">
    <nav>
      <a class="brand" href="./">RISC-V Radar</a>
      <div>
        <a href="#news">News</a>
        <a href="#paper">Papers</a>
        <a href="#tech">Tech</a>
        <a href="#market">Markets</a>
      </div>
    </nav>
    <section class="hero">
      <div>
        <p class="eyebrow">Daily industry intelligence</p>
        <h1>RISC-V Radar</h1>
        <p class="lede">A static daily briefing that tracks public RISC-V news, papers, companies, markets, and engineering activity.</p>
      </div>
      <div class="hero-stats" aria-label="Daily counts">
        <div><strong>{len(items)}</strong><span>Total items</span></div>
        <div><strong>{len(top)}</strong><span>Top signals</span></div>
        <div><strong>{escape(data['date'])}</strong><span>Briefing date</span></div>
      </div>
    </section>
  </header>
  <main>
    <section class="category-nav" aria-label="Categories">{category_nav}</section>
    <section class="top-section">
      <div class="section-heading">
        <h2>Top Signals</h2>
        <span>Generated {fmt_date(data['generated_at'])}</span>
      </div>
      <div class="item-grid featured">{top_cards}</div>
    </section>
    {''.join(sections)}
    {error_html}
  </main>
  <footer>
    <p>Built from public metadata and source links. Keep summaries short, attributed, and traceable.</p>
  </footer>
</body>
</html>
"""


def copy_assets() -> None:
    assets_src = SITE_DIR / "assets"
    assets_dest = DIST_DIR / "assets"
    if assets_dest.exists():
        shutil.rmtree(assets_dest)
    shutil.copytree(assets_src, assets_dest)


def main() -> int:
    global DIST_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DIST_DIR))
    args = parser.parse_args()
    DIST_DIR = Path(args.out)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    copy_assets()
    data = load_latest()
    (DIST_DIR / "index.html").write_text(render_index(data), encoding="utf-8")
    (DIST_DIR / "latest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (DIST_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built site at {DIST_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
