#!/usr/bin/env python3
"""Collect RISC-V radar items from public feeds and APIs."""

from __future__ import annotations

import argparse
import csv
import email.utils
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "sources.json"
RAW_DIR = ROOT / "data" / "raw"
DAILY_DIR = ROOT / "data" / "daily"
USER_AGENT = "riscv-radar/0.1 (+https://github.com/your-name/riscv-radar)"


@dataclass
class Item:
    title: str
    url: str
    source: str
    category: str
    published_at: str
    summary: str = ""
    tags: Optional[list[str]] = None
    entities: Optional[list[str]] = None
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        base = {
            "id": stable_id(self.url or self.title),
            "title": clean_text(self.title),
            "url": self.url,
            "source": self.source,
            "category": self.category,
            "published_at": self.published_at,
            "summary": clean_text(self.summary),
            "tags": self.tags or [],
            "entities": self.entities or [],
            "score": round(self.score, 3),
        }
        return base


def request_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
        return data.decode(encoding, errors="replace")


def clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def parse_date(value: Optional[str]) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    value = value.strip()
    try:
        return email.utils.parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def first_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element.iter():
        if local_name(child.tag) in names and child.text:
            return child.text
    return ""


def first_link(element: ET.Element) -> str:
    for child in element.iter():
        if local_name(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href
            if child.text:
                return child.text
    return ""


def collect_rss(source: dict[str, Any]) -> list[Item]:
    text = request_text(source["url"])
    root = ET.fromstring(text)
    entries = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    items: list[Item] = []
    for entry in entries[:50]:
        title = first_text(entry, ("title",))
        url = first_link(entry)
        published = first_text(entry, ("pubdate", "published", "updated", "dc:date"))
        summary = first_text(entry, ("description", "summary", "content", "encoded"))
        if title and url:
            items.append(
                Item(
                    title=title,
                    url=url,
                    source=source["name"],
                    category=source.get("category", "news"),
                    published_at=parse_date(published),
                    summary=summary,
                    score=float(source.get("weight", 1.0)),
                )
            )
    return items


def collect_arxiv(source: dict[str, Any]) -> list[Item]:
    query = urllib.parse.quote(source["query"])
    max_results = int(source.get("max_results", 20))
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query=all:{query}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    )
    text = request_text(url)
    root = ET.fromstring(text)
    items: list[Item] = []
    for entry in [node for node in root if local_name(node.tag) == "entry"]:
        title = first_text(entry, ("title",))
        link = first_link(entry)
        published = first_text(entry, ("published", "updated"))
        summary = first_text(entry, ("summary",))
        if title and link:
            items.append(
                Item(
                    title=title,
                    url=link,
                    source=source["name"],
                    category=source.get("category", "paper"),
                    published_at=parse_date(published),
                    summary=summary,
                    score=float(source.get("weight", 1.0)),
                )
            )
    return items


def collect_github(source: dict[str, Any]) -> list[Item]:
    query = urllib.parse.quote(source["query"])
    max_results = int(source.get("max_results", 15))
    url = (
        "https://api.github.com/search/repositories?"
        f"q={query}&sort=updated&order=desc&per_page={max_results}"
    )
    data = json.loads(request_text(url))
    items: list[Item] = []
    for repo in data.get("items", []):
        name = repo.get("full_name", "")
        html_url = repo.get("html_url", "")
        updated_at = repo.get("updated_at", "")
        desc = repo.get("description") or ""
        stars = repo.get("stargazers_count", 0)
        if name and html_url:
            items.append(
                Item(
                    title=f"{name} updated on GitHub",
                    url=html_url,
                    source=source["name"],
                    category=source.get("category", "tech"),
                    published_at=parse_date(updated_at),
                    summary=f"{desc} Stars: {stars}.",
                    score=float(source.get("weight", 0.7)),
                )
            )
    return items


def collect_market(source: dict[str, Any]) -> list[Item]:
    symbol = source["symbol"].lower()
    url = f"https://stooq.com/q/l/?s={urllib.parse.quote(symbol)}&f=sd2t2ohlcv&h&e=csv"
    text = request_text(url)
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        return []
    row = rows[0]
    close = row.get("Close", "N/D")
    date = row.get("Date", "")
    volume = row.get("Volume", "N/D")
    title = f"{source['name']} market snapshot: close {close}"
    return [
        Item(
            title=title,
            url=f"https://stooq.com/q/?s={urllib.parse.quote(symbol)}",
            source="Stooq",
            category=source.get("category", "market"),
            published_at=parse_date(date),
            summary=f"{source['name']} ({source['symbol']}) latest close: {close}; volume: {volume}.",
            tags=["market"],
            entities=[source["name"]],
            score=0.35,
        )
    ]


def enrich(item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    text = f"{item['title']} {item.get('summary', '')}"
    lowered = text.lower()
    topics = []
    entities = []
    for topic in config["watchlist"]["topics"]:
        if topic.lower() in lowered:
            topics.append(topic)
    for company in config["watchlist"]["companies"]:
        if company.lower() in lowered:
            entities.append(company)
    category_weights = {"news": 0.4, "paper": 0.45, "tech": 0.5, "startup": 0.45, "market": 0.2}
    score = float(item.get("score", 0.0)) + category_weights.get(item["category"], 0.3)
    score += min(len(topics) * 0.12, 0.48)
    score += min(len(entities) * 0.18, 0.54)
    if "risc-v" in lowered or "riscv" in lowered:
        score += 0.8
    item["tags"] = sorted(set(item.get("tags", []) + topics))[:8]
    item["entities"] = sorted(set(item.get("entities", []) + entities))[:8]
    item["score"] = round(score, 3)
    return item


def is_relevant(item: dict[str, Any]) -> bool:
    if item["category"] in {"paper", "market"}:
        return True
    if item.get("tags") or item.get("entities"):
        return True
    lowered = f"{item['title']} {item.get('summary', '')}".lower()
    return any(term in lowered for term in ("risc-v", "riscv", "risc v"))


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item["url"].split("?", 1)[0].rstrip("/") or item["title"].lower()
        current = seen.get(key)
        if not current or item["score"] > current["score"]:
            seen[key] = item
    return sorted(seen.values(), key=lambda row: (row["score"], row["published_at"]), reverse=True)


def collect_all(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    collected: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    collectors = [
        ("rss", collect_rss),
        ("arxiv", collect_arxiv),
        ("github", collect_github),
        ("markets", collect_market),
    ]
    for section, collector in collectors:
        for source in config.get(section, []):
            if source.get("enabled") is False:
                continue
            try:
                for item in collector(source):
                    enriched = enrich(item.to_dict(), config)
                    if is_relevant(enriched):
                        collected.append(enriched)
            except (urllib.error.URLError, TimeoutError, ET.ParseError, json.JSONDecodeError, csv.Error) as exc:
                errors.append({"source": source.get("name", source.get("url", section)), "error": str(exc)})
    return dedupe(collected), errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    items, errors = collect_all(config)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": args.date,
        "items": items,
        "errors": errors,
    }
    (DAILY_DIR / f"{args.date}.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    (RAW_DIR / "latest.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Collected {len(items)} items with {len(errors)} source errors.")
    for error in errors:
        print(f"WARN {error['source']}: {error['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
