"""
Underlight RAG HTTP server.
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
from http.server import HTTPServer, BaseHTTPRequestHandler
from config_loader import load_config
from rag_core import table_names


cfg = load_config()

# ---------------------------------------------------------------------------
# Embedder + retriever (import from assistant)
# ---------------------------------------------------------------------------
from assistant import retrieve, ask_ollama, build_prompt


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
    MAX_BODY_BYTES = 1024 * 1024

    def do_GET(self):
        if self.path == "/health":
            ollama_ok = False
            tables: list[str] = []
            try:
                import requests
                response = requests.get(
                    f"{cfg['ollama']['base_url'].rstrip('/')}/api/tags", timeout=2
                )
                ollama_ok = response.ok
            except Exception:
                pass
            try:
                import lancedb
                tables = table_names(lancedb.connect(cfg["store"]["dir"]))
            except Exception:
                pass
            self._json(200, {
                "ok": ollama_ok,
                "ollama_ok": ollama_ok,
                "ollama_model": cfg["ollama"]["model"],
                "ollama_base": cfg["ollama"]["base_url"],
                "embedder": cfg["embedder"]["model"],
                "store_dir": cfg["store"]["dir"],
                "store_tables": tables,
            })
        else:
            self._json(404, {"error": "unknown endpoint"})

    def do_POST(self):
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len < 0 or self.headers.get("Transfer-Encoding"):
                raise ValueError
        except ValueError:
            self.close_connection = True
            self._json(400, {"error": "invalid Content-Length or unsupported Transfer-Encoding"})
            return
        if content_len > self.MAX_BODY_BYTES:
            self.close_connection = True
            self._json(413, {"error": "request body too large"})
            return
        body = self.rfile.read(content_len)
        try:
            data = json.loads(body) if body else {}
        except Exception:
            self._json(400, {"error": "invalid JSON"})
            return
        if not isinstance(data, dict):
            self._json(400, {"error": "JSON body must be an object"})
            return

        if self.path == "/ask":
            self._handle_ask(data)
        elif self.path == "/log":
            self._handle_log(data)
        else:
            self._json(404, {"error": "unknown endpoint"})

    def _handle_ask(self, data: dict):
        query = data.get("query")
        if not isinstance(query, str) or not query.strip():
            self._json(400, {"error": "query must be a nonempty string"})
            return
        query = query.strip()

        tables = data.get("tables", cfg["assistant"]["search_tables"])
        if not isinstance(tables, list) or not tables or not all(isinstance(item, str) and item.strip() for item in tables):
            self._json(400, {"error": "tables must be a list of names"})
            return
        top_k = data.get("top_k", cfg["ollama"]["retrieval"]["top_k"])
        if type(top_k) is not int or not 1 <= top_k <= 50:
            self._json(400, {"error": "top_k must be an integer from 1 to 50"})
            return
        min_score = cfg["ollama"]["retrieval"].get("min_score", 0.25)
        remember = data.get("remember", False)
        project = data.get("project", cfg["chat"]["default_project"])
        system = data.get("system_prompt")
        if type(remember) is not bool or not isinstance(project, str) or not project.strip():
            self._json(400, {"error": "remember must be a boolean and project a nonempty string"})
            return
        if system is not None and not isinstance(system, str):
            self._json(400, {"error": "system_prompt must be a string"})
            return

        t0 = time.time()
        try:
            chunks = retrieve(query, tables, top_k=top_k, min_score=min_score)
        except Exception as exc:
            self._json(503, {"error": f"retrieval failed: {exc}"})
            return

        chat_history = None
        if remember:
            try:
                from chat_tracker import query_chat
                chat_history = query_chat(query, top_k=6, project=project)
            except Exception as e:
                print(f"[warn] chat history fetch failed: {e}", file=sys.stderr)

        prompt = build_prompt(query, chunks, chat_history, system_prompt=system)
        try:
            answer = ask_ollama(prompt, max_context=cfg["ollama"].get("max_context_tokens", 4096), raise_on_error=True)
        except Exception as exc:
            self._json(502, {"error": str(exc)})
            return

        if remember:
            for role, text in (("user", query), ("assistant", answer)):
                result = log_chat(project, role, text)
                if "error" in result:
                    self._json(500, {"error": result["error"], "logged": False, "answer": answer})
                    return

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
        if not isinstance(project, str) or not project.strip():
            self._json(400, {"error": "project must be a nonempty string"})
            return
        if not isinstance(role, str) or role not in {"user", "assistant", "system"}:
            self._json(400, {"error": "role must be user, assistant, or system"})
            return
        if not isinstance(text, str) or not text.strip():
            self._json(400, {"error": "text must be a nonempty string"})
            return
        result = log_chat(project, role, text)
        if "error" in result:
            self._json(500, {"logged": False, "error": result["error"]})
            return
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
    parser = argparse.ArgumentParser(description="Underlight RAG HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), RagHandler)
    print(f"Underlight RAG server listening on http://{args.host}:{args.port}")
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
