#!/usr/bin/env python3
"""Translate and editorially summarize the latest RISC-V radar items."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DAILY_DIR = ROOT / "data" / "daily"
DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M3"
BATCH_SIZE = 2


def api_request(base_url: str, api_key: str, model: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prompt_items = [
        {
            "id": item["id"],
            "category": item["category"],
            "title": item["title"],
            "summary": item.get("summary", "")[:900],
            "source": item.get("source", ""),
        }
        for item in items
    ]
    system = (
        "你是一名RISC-V产业研究编辑。请将输入的英文资讯整理成简洁、准确、自然的简体中文。"
        "保留公司名、项目名、标准名、指令集名和技术缩写的英文写法；不要编造输入中没有的事实。"
        "摘要控制在60到110个汉字；值得关注控制在30到60个汉字。"
        "只返回JSON数组，不要Markdown代码块，不要额外解释。"
    )
    user = json.dumps(
        {
            "task": "为每条资讯生成中文标题、中文摘要、值得关注和中文标签。",
            "items": prompt_items,
            "output_schema": [
                {
                    "id": "same id",
                    "title_zh": "中文标题",
                    "summary_zh": "中文摘要",
                    "why_it_matters_zh": "值得关注",
                    "tags_zh": ["中文标签"],
                }
            ],
        },
        ensure_ascii=False,
    )
    payload = json.dumps(
        {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 1800,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "riscv-radar/0.2",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MiniMax HTTP {error.code}: {body[:300]}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"MiniMax connection error: {error.reason}") from error

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("MiniMax returned no choices")
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return parse_json_array(strip_thinking(str(content)))


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def parse_json_array(text: str) -> list[dict[str, Any]]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
    start = cleaned.find("[")
    closing = "]"
    if start < 0:
        start = cleaned.find("{")
        closing = "}"
    end = cleaned.rfind(closing)
    if start < 0 or end <= start:
        raise RuntimeError("MiniMax response did not contain a JSON array")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as error:
        raise RuntimeError(f"MiniMax returned incomplete JSON at character {error.pos}") from error
    if isinstance(parsed, dict):
        parsed = parsed.get("items") or parsed.get("results") or [parsed]
    if not isinstance(parsed, list):
        raise RuntimeError("MiniMax response JSON was not an array or object")
    normalized = []
    for row in parsed:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        normalized.append(
            {
                "id": row["id"],
                "title_zh": row.get("title_zh") or row.get("title", ""),
                "summary_zh": row.get("summary_zh") or row.get("summary", ""),
                "why_it_matters_zh": row.get("why_it_matters_zh") or row.get("why_it_matters", ""),
                "tags_zh": row.get("tags_zh") or row.get("tags", []),
            }
        )
    return normalized


def fallback(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "title_zh": item["title"],
        "summary_zh": item.get("summary", "") or "暂无中文摘要。",
        "why_it_matters_zh": "等待中文编辑摘要。",
        "tags_zh": item.get("tags", [])[:5],
    }


def translate_items(items: list[dict[str, Any]], api_key: str, base_url: str, model: str) -> tuple[int, list[str]]:
    translated: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start : start + BATCH_SIZE]
        try:
            rows = api_request(base_url, api_key, model, batch)
            for row in rows:
                if row.get("id") in {item["id"] for item in batch}:
                    translated[row["id"]] = row
        except RuntimeError as error:
            errors.append(f"batch {start // BATCH_SIZE + 1}: {error}")
        for item in batch:
            item.update(translated.get(item["id"], fallback(item)))
    return len(translated), errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--input", type=Path)
    parser.add_argument("--base-url", default=os.environ.get("MINIMAX_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL))
    parser.add_argument("--retry-missing", action="store_true", help="only retry items without a usable Chinese translation")
    args = parser.parse_args()

    input_path = args.input or DAILY_DIR / f"{args.date}.json"
    data = json.loads(input_path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    if args.retry_missing:
        items = [
            item
            for item in items
            if not item.get("title_zh")
            or item.get("title_zh") == item.get("title")
            or item.get("why_it_matters_zh") == "等待中文编辑摘要。"
        ]
    api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not api_key:
        print("MINIMAX_API_KEY is not set; keeping source text and marking items as untranslated.", file=sys.stderr)
        for item in items:
            item.update(fallback(item))
        errors = ["MINIMAX_API_KEY is not configured"]
        translated_count = 0
    else:
        translated_count, errors = translate_items(items, api_key, args.base_url, args.model)

    usable_translations = sum(
        1 for item in data.get("items", []) if item.get("title_zh") and item.get("title_zh") != item.get("title")
    )
    data["translation"] = {
        "language": "zh-CN",
        "model": args.model,
        "translated_items": usable_translations,
        "total_items": len(data.get("items", [])),
        "errors": errors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    input_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Translated {translated_count}/{len(data.get('items', []))} items with {args.model}.")
    for error in errors:
        print(f"WARN {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
