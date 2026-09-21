"""
Route A — assistant.py (corrected for LanceDB version)
Fixes:
- db.exists_table() doesn't exist -> use _table_exists() helper
- list_tables() returns tuples, extract name string
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from config_loader import load_config

cfg = load_config()

OLLAMA_URL = f"{cfg['ollama']['base_url']}/api/generate"
OLLAMA_TIMEOUT = cfg["ollama"].get("timeout_s", 120)

from sentence_transformers import SentenceTransformer

embedder = SentenceTransformer(
    cfg["embedder"]["model"],
    device=cfg["embedder"]["device"],
)

import lancedb


def _table_exists(db, name: str) -> bool:
    """Check if a LanceDB table exists. list_tables() may return str or tuple."""
    names = db.list_tables()
    for n in names:
        if isinstance(n, tuple):
            if n and n[0] == name:
                return True
        elif isinstance(n, str) and n == name:
            return True
    return False


def retrieve(query: str, tables: list[str], top_k: int = 6,
             min_score: float = 0.25) -> list[dict]:
    """Search multiple LanceDB tables, return scored chunks."""
    db = lancedb.connect(cfg["store"]["dir"])
    emb = embedder.encode([query], convert_to_numpy=True)[0].tolist()
    results: list[dict] = []

    for tbl_name in tables:
        full_name = cfg["store"]["tables"].get(tbl_name, tbl_name)
        if not _table_exists(db, full_name):
            continue
        tbl = db.open_table(full_name)
        hits = tbl.search(emb).limit(top_k * 2).to_list()
        for h in hits:
            score = 1.0 - (h.get("_distance", 1.0) or 1.0)
            if score < min_score:
                continue
            results.append({
                "text": h["text"],
                "source": h.get("source", ""),
                "path": h.get("path", ""),
                "kind": h.get("kind", ""),
                "project": h.get("project", ""),
                "score": round(score, 3),
                "table": tbl_name,
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def build_prompt(query: str, chunks: list[dict], chat_history: list[dict] | None = None,
                 system_prompt: str | None = None) -> str:
    ctx = ""
    if chunks:
        ctx = "## Retrieved context\n\n"
        for i, c in enumerate(chunks, 1):
            meta = ""
            if c.get("source"):
                meta += f" [{c['source']}]"
            if c.get("path"):
                meta += f" ({c['path']})"
            ctx += f"{i}. (score={c['score']:.2f}, {c.get('kind','')}{meta})\n"
            ctx += f"   {c['text']}\n\n"

    history = ""
    if chat_history:
        history = "## Past conversation\n\n"
        for h in chat_history[-6:]:
            role = h.get("role", "user").upper()
            history += f"{role}: {h['text']}\n"
        history += "\n"

    sys_prompt = system_prompt or (
        "You are a practical AI assistant helping a developer/designer who works with code, "
        "KiCad PCB design, digital art, and singing/music. "
        "Use the retrieved context below to ground your answers. "
        "If the context doesn't have the answer, say so and suggest what to check. "
        "Prefer concrete steps, commands, and file paths over vague advice. "
        "When referencing code, quote relevant lines. When referencing KiCad, mention the specific tool/page."
    )

    prompt = f"{sys_prompt}\n\n"
    if ctx:
        prompt += ctx
    if history:
        prompt += history
    prompt += f"## User question\n\n{query}\n\n"
    prompt += "## Answer\n"
    return prompt


def ask_ollama(prompt: str, model: str | None = None,
               max_context: int = 4096) -> str:
    model = model or cfg["ollama"]["model"]
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": max_context,
            "temperature": 0.4,
            "top_p": 0.9,
        },
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
    except requests.exceptions.Timeout:
        return f"[ERROR: Ollama timed out after {OLLAMA_TIMEOUT}s. Model may be loading or context too large.]"
    except requests.exceptions.ConnectionError:
        return f"[ERROR: Cannot reach Ollama at {cfg['ollama']['base_url']}. Is it running?]"
    except Exception as e:
        return f"[ERROR: Ollama call failed: {e}]"


def cmd_answer(args):
    t0 = time.time()

    tables = args.tables or cfg["assistant"]["search_tables"]
    top_k = args.top_k or cfg["ollama"]["retrieval"]["top_k"]
    min_score = cfg["ollama"]["retrieval"].get("min_score", 0.25)

    print(f"[1/3] Retrieving from tables: {tables} ...", file=sys.stderr)
    chunks = retrieve(args.query, tables, top_k=top_k, min_score=min_score)
    print(f"  -> {len(chunks)} chunks retrieved in {time.time()-t0:.2f}s", file=sys.stderr)

    if args.verbose:
        for c in chunks:
            print(f"\n--- chunk (score={c['score']}) ---", file=sys.stderr)
            print(f"  source: {c['source']}", file=sys.stderr)
            print(f"  kind: {c['kind']}", file=sys.stderr)
            print(f"  text: {c['text'][:200]}...", file=sys.stderr)

    chat_history = None
    if args.remember:
        print("[2/3] Fetching chat history ...", file=sys.stderr)
        chat_history = query_chat(args.query, top_k=6, project=args.project)
        print(f"  -> {len(chat_history) if chat_history else 0} past messages", file=sys.stderr)

    prompt = build_prompt(args.query, chunks, chat_history)

    print(f"[3/3] Asking Ollama ({cfg['ollama']['model']}) ...", file=sys.stderr)
    answer = ask_ollama(prompt)
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"[{elapsed:.1f}s]")
    print(f"{'='*60}")
    print(answer)

    if args.remember and cfg["chat"]["auto_log"]:
        from chat_tracker import log_message
        log_message(args.project or cfg["chat"]["default_project"],
                    "user", args.query)
        log_message(args.project or cfg["chat"]["default_project"],
                    "assistant", answer)
        print(f"\n[logged to chat project '{args.project or cfg['chat']['default_project']}']",
              file=sys.stderr)
    elif args.remember:
        print("\n[remembered: set --remember to auto-log]", file=sys.stderr)


def cmd_ask_ollama(args):
    prompt = args.prompt or "Hello, what can you help me with?"
    print("Asking Ollama directly ...", file=sys.stderr)
    answer = ask_ollama(prompt)
    print(answer)


def main():
    parser = argparse.ArgumentParser(description="Route A assistant CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_answer = sub.add_parser("answer", help="Query with retrieval + Ollama")
    p_answer.add_argument("query")
    p_answer.add_argument("--tables", default=None,
                          help="comma-separated table names")
    p_answer.add_argument("--top-k", type=int, default=None)
    p_answer.add_argument("--remember", action="store_true",
                          help="include chat history + log this exchange")
    p_answer.add_argument("--project", default=None)
    p_answer.add_argument("--verbose", action="store_true")

    p_ask = sub.add_parser("ask", help="Direct Ollama query (no retrieval)")
    p_ask.add_argument("prompt", nargs="?", default=None)

    args = parser.parse_args()
    if args.cmd == "answer":
        cmd_answer(args)
    elif args.cmd == "ask":
        cmd_ask_ollama(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
