#!/usr/bin/env python3
"""Tiny local adapter from OpenAI Responses SSE to MiniMax chat completions.

This exists because Open Design's Codex agent uses Codex CLI, and the current
Codex CLI custom provider path speaks `/v1/responses`. MiniMax-M3 is available
through OpenAI-compatible `/v1/chat/completions`, so this proxy translates the
small subset needed for Open Design text generation.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "MiniMax-M3"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimaxi.com/v1"


def load_open_design_key() -> str:
    config_path = (
        Path.home()
        / "Library/Application Support/Open Design/namespaces/release-stable/data/app-config.json"
    )
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        key = data.get("agentCliEnv", {}).get("codex", {}).get("OPENAI_API_KEY", "")
        if isinstance(key, str) and key.strip():
            return key.strip()
    except Exception:
        pass
    return os.environ.get("MINIMAX_API_KEY", "").strip()


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("input_text") or item.get("output_text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    return ""


def responses_input_to_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    raw_input = payload.get("input")
    if isinstance(raw_input, str):
        messages.append({"role": "user", "content": raw_input})
    elif isinstance(raw_input, list):
        for item in raw_input:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in {"system", "user", "assistant", "developer"}:
                role = "user"
            if role == "developer":
                role = "system"
            content = text_from_content(item.get("content"))
            if content:
                messages.append({"role": role, "content": content})

    if not any(message["role"] == "user" for message in messages):
        messages.append({"role": "user", "content": "Continue."})
    return messages


def sse_event(name: str, data: dict[str, Any]) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def strip_thinking(text: str) -> str:
    while True:
        start = text.find("<think>")
        if start < 0:
            return text
        end = text.find("</think>", start)
        if end < 0:
            return text[:start]
        text = text[:start] + text[end + len("</think>") :]


def normalize_output(text: str) -> str:
    return strip_thinking(text).lstrip()


def done_response(response_id: str, model: str, text: str, usage: dict[str, Any] | None = None) -> list[bytes]:
    item = {
        "id": "msg_0",
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    }
    response = {
        "id": response_id,
        "object": "response",
        "status": "completed",
        "model": model,
        "output": [item],
        "usage": usage or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }
    return [
        sse_event("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": "msg_0",
            "output_index": 0,
            "content_index": 0,
            "text": text,
        }),
        sse_event("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": "msg_0",
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": text},
        }),
        sse_event("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": item,
        }),
        sse_event("response.completed", {"type": "response.completed", "response": response}),
        b"data: [DONE]\n\n",
    ]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path.startswith("/v1/models"):
            body = json.dumps({"data": [{"id": DEFAULT_MODEL, "object": "model"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/responses":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        model = payload.get("model") if isinstance(payload.get("model"), str) else DEFAULT_MODEL
        response_id = f"resp_{int(time.time() * 1000)}"

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        start = {
            "id": response_id,
            "object": "response",
            "status": "in_progress",
            "model": model,
            "output": [],
        }
        self.wfile.write(sse_event("response.created", {"type": "response.created", "response": start}))
        self.wfile.write(sse_event("response.output_item.added", {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": "msg_0", "type": "message", "status": "in_progress", "role": "assistant", "content": []},
        }))
        self.wfile.write(sse_event("response.content_part.added", {
            "type": "response.content_part.added",
            "item_id": "msg_0",
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": ""},
        }))
        self.wfile.flush()

        try:
            for chunk in self.proxy_minimax(payload, model):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return
        except urllib.error.HTTPError as exc:
            body = exc.read(1000).decode("utf-8", errors="replace")
            message = f"MiniMax HTTP {exc.code}: {body}"
            print(f"[minimax-proxy] upstream HTTP {exc.code}: {body}", file=sys.stderr, flush=True)
            self.write_error_event(message)
        except Exception as exc:
            message = f"MiniMax proxy error: {exc}"
            print(f"[minimax-proxy] {message}", file=sys.stderr, flush=True)
            self.write_error_event(message)

    def write_error_event(self, message: str) -> None:
        error = {
            "type": "error",
            "code": "UPSTREAM_UNAVAILABLE",
            "message": message,
        }
        try:
            self.wfile.write(sse_event("error", error))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return

    def proxy_minimax(self, payload: dict[str, Any], model: str) -> list[bytes]:
        key = load_open_design_key()
        if not key:
            raise RuntimeError("MiniMax API key is missing")

        request_body = {
            "model": model or DEFAULT_MODEL,
            "messages": responses_input_to_messages(payload),
            "stream": True,
        }
        max_tokens = payload.get("max_output_tokens") or payload.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            request_body["max_tokens"] = max_tokens

        base_url = os.environ.get("MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL).rstrip("/")
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )

        raw_output = ""
        emitted_len = 0
        usage: dict[str, Any] | None = None
        with urllib.request.urlopen(req, timeout=120) as response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                usage = event.get("usage") if isinstance(event.get("usage"), dict) else usage
                for choice in event.get("choices", []):
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta", {})
                    text = delta.get("content") if isinstance(delta, dict) else None
                    if not isinstance(text, str) or not text:
                        continue
                    raw_output += text
                    visible_output = normalize_output(raw_output)
                    delta = visible_output[emitted_len:]
                    if not delta:
                        continue
                    emitted_len = len(visible_output)
                    yield sse_event("response.output_text.delta", {
                        "type": "response.output_text.delta",
                        "item_id": "msg_0",
                        "output_index": 0,
                        "content_index": 0,
                        "delta": delta,
                    })

        output = normalize_output(raw_output)
        yield from done_response(payload.get("id") or f"resp_{int(time.time() * 1000)}", model, output, usage)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[minimax-proxy] " + fmt % args + "\n")


def main() -> int:
    port = int(os.environ.get("MINIMAX_PROXY_PORT", "8787"))
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"MiniMax Responses proxy listening on http://127.0.0.1:{port}/v1", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
