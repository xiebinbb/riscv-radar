#!/usr/bin/env python3
"""Small static output check for CI and local sanity."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "dist" / "index.html"


def main() -> int:
    html = INDEX.read_text(encoding="utf-8")
    required = ["RISC-V Radar", "Top Signals", "News", "Papers", "Markets"]
    missing = [text for text in required if text not in html]
    if missing:
        raise SystemExit(f"Missing expected page text: {', '.join(missing)}")
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
