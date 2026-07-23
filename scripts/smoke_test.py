#!/usr/bin/env python3
"""Small static output check for CI and local sanity."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "dist" / "index.html"
OBSIDIAN_INDEX = ROOT / "obsidian-vault" / "index.md"


def main() -> int:
    html = INDEX.read_text(encoding="utf-8")
    required = ["RISC-V Radar", "重点信号", "新闻", "论文", "市场", "值得关注"]
    missing = [text for text in required if text not in html]
    if missing:
        raise SystemExit(f"Missing expected page text: {', '.join(missing)}")
    if OBSIDIAN_INDEX.exists() and "RISC-V Radar 知识库" not in OBSIDIAN_INDEX.read_text(encoding="utf-8"):
        raise SystemExit("Obsidian index is missing its title")
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
