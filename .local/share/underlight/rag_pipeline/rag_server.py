"""
Route A — rag_server.py
Lightweight HTTP API for the assistant: query → retrieve → Ollama → answer.
Useful for Hermes tool calls, curl, or any client.

Endpoints:
  POST /ask
    {"query": "...", "tables": ["projects","downloads"], "top_k": 6, "remember": true}
    → {"answer": "...", "elapsed_s": 2.3, "chunks": [...]}

  GET /health
    → {"ok": true, "ollama_model": "qwen3:4b", "store_tables": [...]}

  POST /log
    {"project": "default", "role": "user", "text": "..."}
    → {"logged": true}

Run:  python rag_server.py [--host 0.0.0.0] [--port 8080]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from http.server import HTTPServer, BaseHTTPRequestHandler
from config_loader import load_config


cfg = load_config()

# ---------------------------------------------------------------------------
# Embedder + retriever (import from assistant)
# ---------------------------------------------------------------------------
from assistant import retrieve, ask_ollama, build_prompt, embedder


# ---------------------------------------------------------------------------
# Chat logging (import from chat_tracker)
# ---------------------------------------------------------------------------
def log_chat(project: str, role: str, text: str) -> dict:
    try:
        from chat_tracker import log_message
        return log_message(project, role, text)
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class RagHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._json(200, {
                "ok": True,
                "ollama_model": cfg["ollama"]["model"],
                "ollama_base": cfg["ollama"]["base_url"],
                "embedder": cfg["embedder"]["model"],
                "store_dir": cfg["store"]["dir"],
                "store_tables": list(cfg["store"]["tables"].values()),
            })
        else:
            self._json(404, {"error": "unknown endpoint"})

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)
        try:
            data = json.loads(body) if body else {}
        except Exception:
            self._json(400, {"error": "invalid JSON"})
            return

        if self.path == "/ask":
            self._handle_ask(data)
        elif self.path == "/log":
            self._handle_log(data)
        else:
            self._json(404, {"error": "unknown endpoint"})

    def _handle_ask(self, data: dict):
        query = data.get("query", "").strip()
        if not query:
            self._json(400, {"error": "query required"})
            return

        tables = data.get("tables") or cfg["assistant"]["search_tables"]
        top_k = data.get("top_k") or cfg["ollama"]["retrieval"]["top_k"]
        min_score = cfg["ollama"]["retrieval"].get("min_score", 0.25)
        remember = data.get("remember", False)
        project = data.get("project") or cfg["chat"]["default_project"]
        system = data.get("system_prompt")

        t0 = time.time()
        chunks = retrieve(query, tables, top_k=top_k, min_score=min_score)

        chat_history = None
        if remember:
            try:
                from chat_tracker import query_chat
                chat_history = query_chat(query, top_k=6, project=project)
            except Exception as e:
                print(f"[warn] chat history fetch failed: {e}", file=sys.stderr)

        prompt = build_prompt(query, chunks, chat_history, system_prompt=system)
        answer = ask_ollama(prompt)

        if remember:
            log_chat(project, "user", query)
            log_chat(project, "assistant", answer)

        elapsed = time.time() - t0
        self._json(200, {
            "answer": answer,
            "elapsed_s": round(elapsed, 2),
            "chunks_count": len(chunks),
            "chunks": chunks[:3],  # snippet
        })

    def _handle_log(self, data: dict):
        project = data.get("project", cfg["chat"]["default_project"])
        role = data.get("role", "user")
        text = data.get("text", "")
        if not text:
            self._json(400, {"error": "text required"})
            return
        result = log_chat(project, role, text)
        self._json(200, {"logged": True, "result": result})

    def _json(self, code: int, obj: dict):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        # suppress default stderr spam
        pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Route A RAG HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), RagHandler)
    print(f"Route A RAG server listening on http://{args.host}:{args.port}")
    print(f"  POST /ask  — query with retrieval + Ollama")
    print(f"  POST /log  — log a chat message")
    print(f"  GET  /health — status")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
