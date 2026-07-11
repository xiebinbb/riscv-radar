# Open Design + MiniMax-M3

Open Design stores user-level app config here:

```text
~/Library/Application Support/Open Design/namespaces/release-stable/data/app-config.json
```

The current local config has been prepared for the `codex` agent through a local MiniMax proxy:

```json
{
  "agentId": "codex",
  "agentModels": {
    "codex": {
      "model": "MiniMax-M3",
      "reasoning": "default"
    }
  },
  "agentCliEnv": {
    "codex": {
      "CODEX_HOME": "~/Library/Application Support/Open Design/codex-minimax-home",
      "CODEX_BIN": "/Applications/Codex.app/Contents/Resources/codex",
      "OPENAI_BASE_URL": "http://127.0.0.1:8787/v1",
      "OPENAI_API_KEY": "configured locally"
    }
  }
}
```

Why the proxy exists: Open Design's `codex` agent invokes Codex CLI, and this Codex CLI custom-provider path uses the OpenAI Responses API (`/v1/responses`). MiniMax-M3 is exposed through OpenAI-compatible Chat Completions (`/v1/chat/completions`). The local proxy translates the required Responses SSE events to MiniMax Chat Completions.

Proxy files:

```text
~/Library/Application Support/Open Design/bin/minimax_responses_proxy.py
~/Library/LaunchAgents/io.local.minimax-responses-proxy.plist
```

Source copy in this project:

```text
tools/minimax_responses_proxy.py
tools/start_minimax_proxy.sh
```

Check service state:

```bash
launchctl print gui/$(id -u)/io.local.minimax-responses-proxy
lsof -iTCP:8787 -sTCP:LISTEN -n -P
```

For international MiniMax accounts, use:

```text
https://api.minimax.io/v1
```

For China-region MiniMax accounts, use:

```text
https://api.minimaxi.com/v1
```

The previous configs were backed up beside `app-config.json` with timestamped `.backup-YYYYMMDD-HHMMSS` suffixes.
