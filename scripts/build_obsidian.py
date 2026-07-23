#!/usr/bin/env python3
"""Build an Obsidian-compatible daily knowledge base from radar JSON."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DAILY_DIR = ROOT / "data" / "daily"
VAULT_DIR = ROOT / "obsidian-vault"
NOTE_DIR = VAULT_DIR / "daily"
CATEGORIES = {
    "news": "新闻",
    "paper": "论文",
    "startup": "初创与公司",
    "market": "市场",
    "tech": "技术",
}


def md_text(value: Any) -> str:
    text = str(value or "")
    return re.sub(r"([\\`*_[\]#])", r"\\\1", text).strip()


def yaml_value(value: Any) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def fmt_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return value[:10]


def select_input(date: str | None, explicit: Path | None) -> tuple[Path, str]:
    if explicit:
        path = explicit.resolve()
        return path, date or path.stem
    if date:
        path = DAILY_DIR / f"{date}.json"
        if not path.exists():
            raise SystemExit(f"No daily data found for {date}: {path}")
        return path, date
    files = sorted(DAILY_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No daily data found. Run scripts/collect.py first.")
    return files[-1], files[-1].stem


def item_block(item: dict[str, Any], number: int, highlight_ids: set[str]) -> str:
    category = CATEGORIES.get(item.get("category", ""), item.get("category", "其他"))
    title = md_text(item.get("title_zh") or item.get("title") or "未命名资讯")
    summary = md_text(item.get("summary_zh") or item.get("summary") or "暂无摘要。")
    why = md_text(item.get("why_it_matters_zh") or "暂无重点判断。")
    tags = item.get("tags_zh") or item.get("tags") or []
    tag_text = " ".join(f"`{md_text(tag)}`" for tag in tags[:8])
    source = md_text(item.get("source", "未知来源"))
    url = str(item.get("url", "")).strip()
    marker = " ⭐" if item.get("id") in highlight_ids else ""
    return f"""### {number}. {title}{marker}

- **类型**：{category}
- **来源**：{source}
- **发布时间**：{fmt_date(item.get('published_at', ''))}
- **标签**：{tag_text or '`未分类`'}

**中文摘要**

{summary}

**值得关注**

{why}

**原文**：[打开来源]({url})

"""


def render_daily(data: dict[str, Any], date: str) -> str:
    items = data.get("items", [])
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in CATEGORIES}
    for item in items:
        groups.setdefault(item.get("category", "other"), []).append(item)
    highlights = {item.get("id") for item in items[:8]}
    counts = Counter(CATEGORIES.get(item.get("category", ""), "其他") for item in items)
    translation = data.get("translation", {})
    errors = data.get("errors", []) + translation.get("errors", [])

    overview = "\n".join(f"- **{name}**：{counts.get(name, 0)} 条" for name in CATEGORIES.values())
    error_note = "\n> [!warning] 数据源或翻译警告\n> " + "；".join(md_text(row.get("error", row)) for row in errors) if errors else ""
    sections = []
    for key, label in CATEGORIES.items():
        section_items = groups.get(key, [])
        if not section_items:
            continue
        sections.append(f"## {label}\n\n")
        sections.extend(item_block(item, index, highlights) for index, item in enumerate(section_items, 1))

    return f"""---
type: riscv-radar-daily
date: {yaml_value(date)}
generated_at: {yaml_value(data.get('generated_at', ''))}
translation_model: {yaml_value(translation.get('model', ''))}
item_count: {len(items)}
tags:
  - riscv
  - daily-briefing
  - industry-radar
---

# RISC-V 日报 | {date}

> 自动生成的 RISC-V 产业情报笔记。原始数据保存在 `data/daily/{date}.json`，每条内容都保留原文链接。

## 今日概览

- **资讯总数**：{len(items)} 条
- **中文翻译**：{translation.get('translated_items', 0)}/{translation.get('total_items', len(items))} 条
- **生成时间**：{fmt_date(data.get('generated_at', ''))}

{overview}
{error_note}

## 重点信号

""" + "\n".join(
        f"- **{md_text(item.get('title_zh') or item.get('title'))}**：{md_text(item.get('why_it_matters_zh') or item.get('summary_zh') or item.get('summary'))}"
        for item in items[:8]
    ) + "\n\n" + "\n".join(sections)


def render_index(data_files: list[Path]) -> str:
    rows = []
    for path in reversed(data_files):
        data = json.loads(path.read_text(encoding="utf-8"))
        date = data.get("date", path.stem)
        items = data.get("items", [])
        translated = data.get("translation", {}).get("translated_items", 0)
        rows.append(f"- [[daily/{date}|{date}]] · {len(items)} 条资讯 · {translated} 条中文翻译")
    return """---
type: riscv-radar-index
tags:
  - riscv
  - index
---

# RISC-V Radar 知识库

这里保存 RISC-V Radar 每日生成的中文产业情报。Obsidian 会自动索引标题、正文、标签和 YAML 元数据。

## 每日简报

""" + "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="daily data date; defaults to the newest JSON")
    parser.add_argument("--input", type=Path, help="explicit daily JSON path")
    parser.add_argument("--vault", type=Path, default=VAULT_DIR)
    args = parser.parse_args()

    input_path, date = select_input(args.date, args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    vault = args.vault.resolve()
    note_dir = vault / "daily"
    note_dir.mkdir(parents=True, exist_ok=True)
    (note_dir / f"{date}.md").write_text(render_daily(data, date), encoding="utf-8")

    data_files = sorted(DAILY_DIR.glob("*.json"))
    (vault / "index.md").write_text(render_index(data_files), encoding="utf-8")
    print(f"Built Obsidian note: {note_dir / f'{date}.md'}")
    print(f"Updated Obsidian index: {vault / 'index.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
