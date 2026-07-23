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
    "news": "新闻",
    "paper": "论文",
    "startup": "初创与公司",
    "market": "市场",
    "tech": "技术",
}


def load_latest() -> dict[str, Any]:
    files = sorted(DAILY_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No daily data found. Run scripts/collect.py first.")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def load_archive() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    files = sorted(DAILY_DIR.glob("*.json"))
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        briefing_date = data.get("date", path.stem)
        for item in data.get("items", []):
            archived = dict(item)
            archived["briefing_date"] = briefing_date
            items.append(archived)
    items.sort(key=lambda item: (item.get("published_at", ""), item.get("score", 0)), reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": len(files),
        "items": items,
    }


def fmt_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return value[:10]


def item_card(item: dict[str, Any]) -> str:
    tags = "".join(f"<span>{escape(tag)}</span>" for tag in item.get("tags", [])[:5])
    entities = ", ".join(escape(entity) for entity in item.get("entities", [])[:4])
    entity_html = f"<p class=\"entities\">{entities}</p>" if entities else ""
    title = escape(item.get("title_zh") or item.get("title") or "未命名资讯")
    summary = escape(item.get("summary_zh") or item.get("summary") or "暂无摘要。")
    why_it_matters = escape(item.get("why_it_matters_zh") or "")
    why_html = f'<p class="why"><strong>值得关注</strong>{why_it_matters}</p>' if why_it_matters else ""
    return f"""
      <article class="item-card">
        <div class="item-meta">
          <span>{escape(CATEGORIES.get(item['category'], item['category'].title()))}</span>
          <span>{escape(item['source'])}</span>
          <span>{fmt_date(item['published_at'])}</span>
        </div>
        <h3><a href="{escape(item['url'])}" rel="noopener noreferrer" target="_blank">{title}</a></h3>
        <p>{summary}</p>
        {why_html}
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
              <span>{len(groups.get(key, []))} 条</span>
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
        error_html = f"<details class=\"errors\"><summary>数据源警告</summary><ul>{rows}</ul></details>"

    return f"""<!doctype html>
<html lang="zh-CN">
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
        <a href="#news">新闻</a>
        <a href="#paper">论文</a>
        <a href="#tech">技术</a>
        <a href="#market">市场</a>
        <a href="search.html">搜索</a>
      </div>
    </nav>
    <section class="hero">
      <div>
        <p class="eyebrow">每日产业情报</p>
        <h1>RISC-V Radar</h1>
        <p class="lede">追踪 RISC-V 新闻、论文、公司、市场与工程动态的每日中文简报。</p>
      </div>
      <div class="hero-stats" aria-label="Daily counts">
        <div><strong>{len(items)}</strong><span>资讯总数</span></div>
        <div><strong>{len(top)}</strong><span>重点信号</span></div>
        <div><strong>{escape(data['date'])}</strong><span>简报日期</span></div>
      </div>
    </section>
  </header>
  <main>
    <section class="category-nav" aria-label="Categories">{category_nav}</section>
    <section class="top-section">
      <div class="section-heading">
        <h2>重点信号</h2>
        <span>生成于 {fmt_date(data['generated_at'])}</span>
      </div>
      <div class="item-grid featured">{top_cards}</div>
    </section>
    {''.join(sections)}
    {error_html}
  </main>
  <footer>
    <p>内容基于公开元数据与来源链接生成。摘要保持简洁，并保留可追溯来源。</p>
  </footer>
</body>
</html>
"""


def render_search() -> str:
    category_labels = json.dumps(CATEGORIES, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>搜索 | RISC-V Radar</title>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
  <header class="site-header compact-header">
    <nav>
      <a class="brand" href="./">RISC-V Radar</a>
      <div>
        <a href="./">首页</a>
        <a href="search.html" aria-current="page">搜索</a>
      </div>
    </nav>
    <section class="search-hero">
      <p class="eyebrow">历史情报检索</p>
      <h1>搜索 RISC-V Radar</h1>
      <p class="lede">搜索已保存的每日资讯、中文摘要、重点判断、标签和来源。</p>
    </section>
  </header>
  <main>
    <form class="search-form" id="search-form">
      <label class="search-query">
        <span>关键词</span>
        <input id="query" type="search" placeholder="例如：RVV、芯片、AI 加速器" autocomplete="off">
      </label>
      <label>
        <span>分类</span>
        <select id="category">
          <option value="all">全部分类</option>
        </select>
      </label>
      <label>
        <span>来源</span>
        <select id="source">
          <option value="all">全部来源</option>
        </select>
      </label>
      <button type="submit">搜索</button>
    </form>
    <div class="search-toolbar">
      <span id="search-status">正在加载历史索引…</span>
      <button class="clear-button" id="clear-search" type="button">清除条件</button>
    </div>
    <section class="search-results" id="search-results" aria-live="polite"></section>
  </main>
  <footer>
    <p>搜索内容来自已归档的每日 RISC-V Radar 数据。</p>
  </footer>
  <script>
    const CATEGORY_LABELS = {category_labels};
    const queryInput = document.querySelector("#query");
    const categorySelect = document.querySelector("#category");
    const sourceSelect = document.querySelector("#source");
    const resultContainer = document.querySelector("#search-results");
    const status = document.querySelector("#search-status");
    const clearButton = document.querySelector("#clear-search");
    let archiveItems = [];

    function escapeHtml(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function searchableText(item) {{
      return [
        item.title_zh, item.title, item.summary_zh, item.summary,
        item.why_it_matters_zh, item.source, item.briefing_date,
        ...(item.tags_zh || []), ...(item.tags || []), ...(item.entities || [])
      ].join(" ").toLocaleLowerCase("zh-CN");
    }}

    function resultCard(item) {{
      const category = CATEGORY_LABELS[item.category] || item.category || "其他";
      const title = item.title_zh || item.title || "未命名资讯";
      const summary = item.summary_zh || item.summary || "暂无摘要。";
      const why = item.why_it_matters_zh || "";
      const tags = [...(item.tags_zh || []), ...(item.tags || [])]
        .filter((tag, index, all) => all.indexOf(tag) === index)
        .slice(0, 6)
        .map(tag => `<span>${{escapeHtml(tag)}}</span>`).join("");
      return `<article class="search-result">
        <div class="item-meta"><span>${{escapeHtml(category)}}</span><span>${{escapeHtml(item.source)}}</span><span>${{escapeHtml((item.published_at || item.briefing_date || "").slice(0, 10))}}</span></div>
        <h2><a href="${{escapeHtml(item.url)}}" rel="noopener noreferrer" target="_blank">${{escapeHtml(title)}}</a></h2>
        <p>${{escapeHtml(summary)}}</p>
        ${{why ? `<p class="why"><strong>值得关注</strong>${{escapeHtml(why)}}</p>` : ""}}
        <div class="tag-row">${{tags}}</div>
      </article>`;
    }}

    function updateUrl() {{
      const params = new URLSearchParams();
      if (queryInput.value.trim()) params.set("q", queryInput.value.trim());
      if (categorySelect.value !== "all") params.set("category", categorySelect.value);
      if (sourceSelect.value !== "all") params.set("source", sourceSelect.value);
      const next = params.toString() ? `search.html?${{params.toString()}}` : "search.html";
      history.replaceState(null, "", next);
    }}

    function renderResults() {{
      const query = queryInput.value.trim().toLocaleLowerCase("zh-CN");
      const category = categorySelect.value;
      const source = sourceSelect.value;
      const matches = archiveItems.filter(item =>
        (!query || searchableText(item).includes(query)) &&
        (category === "all" || item.category === category) &&
        (source === "all" || item.source === source)
      );
      status.textContent = `找到 ${{matches.length}} 条资讯，共归档 ${{archiveItems.length}} 条`;
      resultContainer.innerHTML = matches.length
        ? matches.slice(0, 100).map(resultCard).join("")
        : `<div class="search-empty"><h2>没有找到匹配内容</h2><p>换一个关键词，或清除分类和来源筛选。</p></div>`;
      updateUrl();
    }}

    function populateFilters() {{
      Object.entries(CATEGORY_LABELS).forEach(([value, label]) => {{
        categorySelect.insertAdjacentHTML("beforeend", `<option value="${{escapeHtml(value)}}">${{escapeHtml(label)}}</option>`);
      }});
      [...new Set(archiveItems.map(item => item.source).filter(Boolean))].sort().forEach(source => {{
        sourceSelect.insertAdjacentHTML("beforeend", `<option value="${{escapeHtml(source)}}">${{escapeHtml(source)}}</option>`);
      }});
    }}

    async function init() {{
      try {{
        const response = await fetch("archive.json", {{ cache: "no-store" }});
        if (!response.ok) throw new Error("archive unavailable");
        const archive = await response.json();
        archiveItems = archive.items || [];
        populateFilters();
        const params = new URLSearchParams(location.search);
        queryInput.value = params.get("q") || "";
        categorySelect.value = params.get("category") || "all";
        sourceSelect.value = params.get("source") || "all";
        renderResults();
      }} catch (error) {{
        status.textContent = "历史索引暂时不可用";
        resultContainer.innerHTML = `<div class="search-empty"><h2>无法加载搜索索引</h2><p>请稍后刷新页面。</p></div>`;
      }}
    }}

    document.querySelector("#search-form").addEventListener("submit", event => {{ event.preventDefault(); renderResults(); }});
    [queryInput, categorySelect, sourceSelect].forEach(control => control.addEventListener("input", renderResults));
    clearButton.addEventListener("click", () => {{ queryInput.value = ""; categorySelect.value = "all"; sourceSelect.value = "all"; renderResults(); }});
    init();
  </script>
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
    archive = load_archive()
    (DIST_DIR / "archive.json").write_text(json.dumps(archive, indent=2, ensure_ascii=False), encoding="utf-8")
    (DIST_DIR / "search.html").write_text(render_search(), encoding="utf-8")
    (DIST_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built site at {DIST_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
