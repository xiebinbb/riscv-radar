#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$HOME/Library/Application Support/Open Design/namespaces/release-stable/logs"
mkdir -p "$LOG_DIR"

exec /usr/bin/python3 "$ROOT/tools/minimax_responses_proxy.py" \
  >> "$LOG_DIR/minimax-responses-proxy.log" 2>&1
