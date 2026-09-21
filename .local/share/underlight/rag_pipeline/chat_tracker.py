"""
Route A — chat_tracker.py (corrected for LanceDB version)
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config_loader import load_config


cfg = load_config()

import lancedb
from sentence_transformers import SentenceTransformer

embedder = SentenceTransformer(
    cfg["embedder"]["model"],
    device=cfg["embedder"]["device"],
)


def _table_exists(db, name: str) -> bool:
    names = db.list_tables()
    for n in names:
        if isinstance(n, tuple):
            if n and n[0] == name:
                return True
        elif isinstance(n, str) and n == name:
            return True
    return False


LOG_DIR = Path(cfg["chat"]["log_dir"]).expanduser()
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _log_path(project: str) -> Path:
    safe = project.replace("/", "_").replace("\\", "_").replace(" ", "_")
    return LOG_DIR / f"{safe}.jsonl"


def log_message(project: str, role: str, text: str,
                metadata: dict | None = None) -> dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "role": role,
        "text": text,
        "metadata": metadata or {},
    }
    path = _log_path(project)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    emb = embedder.encode([text], convert_to_numpy=True)[0].tolist()
    store_msg(project, entry, emb)
    return entry


def store_msg(project: str, entry: dict, embedding: list[float]):
    db = lancedb.connect(cfg["store"]["dir"])
    tbl_name = cfg["store"]["tables"]["chat"]

    tbl = db.create_table(tbl_name, exist_ok=True)

    import pyarrow as pa
    if tbl.schema is None:
        tbl = db.create_table(tbl_name, schema=pa.schema([
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("role", pa.string()),
            pa.field("project", pa.string()),
            pa.field("timestamp", pa.string()),
            pa.field("metadata", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), 384)),
        ]))

    doc_id = f"chat_{entry['timestamp']}_{project}_{len(entry['text'])}"
    tbl.add(pa.Table.from_pylist([{
        "id": doc_id,
        "text": entry["text"],
        "role": entry["role"],
        "project": project,
        "timestamp": entry["timestamp"],
        "metadata": json.dumps(entry.get("metadata", {})),
        "embedding": embedding,
    }]))


def read_log(project: str, limit: int = 200) -> list[dict]:
    path = _log_path(project)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return []
    entries = [json.loads(l) for l in lines[-limit:]]
    return entries


def list_projects() -> list[str]:
    if not LOG_DIR.exists():
        return []
    return sorted(p.stem for p in LOG_DIR.glob("*.jsonl"))


def query_chat(query: str, top_k: int = 8, project: str | None = None) -> list[dict]:
    db = lancedb.connect(cfg["store"]["dir"])
    tbl_name = cfg["store"]["tables"]["chat"]
    if not _table_exists(db, tbl_name):
        return []
    tbl = db.open_table(tbl_name)

    emb = embedder.encode([query], convert_to_numpy=True)[0].tolist()
    top_k = min(top_k, cfg["chat"]["retrieval_top_k"])

    results = tbl.search(emb).limit(top_k).to_list()
    out = []
    for r in results:
        rec = {
            "text": r["text"],
            "role": r["role"],
            "project": r["project"],
            "timestamp": r["timestamp"],
            "score": r.get("_distance", 0),
            "metadata": json.loads(r.get("metadata", "{}")),
        }
        if project and rec["project"] != project:
            continue
        out.append(rec)
    return out


def cmd_log(args):
    entry = log_message(args.project, args.role, args.text,
                        metadata={"context": args.context or ""})
    print(f"Logged [{args.role}] to project '{args.project}': "
          f"{entry['text'][:80]}{'...' if len(entry['text']) > 80 else ''}")
    print(f"  path: {_log_path(args.project)}")


def cmd_query(args):
    results = query_chat(args.query, top_k=args.top, project=args.project)
    if not results:
        print("No past conversations found.")
        return
    print(f"Found {len(results)} relevant past messages:\n")
    for i, r in enumerate(results, 1):
        role_tag = f"[{r['role'].upper()}]"
        print(f"{i}. {role_tag} ({r['project']}, {r['timestamp']}) score={r['score']:.3f}")
        print(f"   {r['text']}")
        if r.get("metadata"):
            print(f"   meta: {r['metadata']}")
        print()


def cmd_list(args):
    projs = list_projects()
    if not projs:
        print("No chat logs yet.")
        return
    print("Chat projects:")
    for p in projs:
        path = _log_path(p)
        n = len(path.read_text(encoding="utf-8").strip().splitlines()) if path.exists() else 0
        print(f"  - {p} ({n} messages)")


def main():
    parser = argparse.ArgumentParser(description="Route A chat tracker")
    sub = parser.add_subparsers(dest="cmd")

    p_log = sub.add_parser("log", help="Log a conversation message")
    p_log.add_argument("--project", default=cfg["chat"]["default_project"])
    p_log.add_argument("--role", required=True, choices=["user", "assistant", "system"])
    p_log.add_argument("--text", required=True)
    p_log.add_argument("--context", default="")

    p_query = sub.add_parser("query", help="Search past conversations")
    p_query.add_argument("query")
    p_query.add_argument("--top", type=int, default=8)
    p_query.add_argument("--project")

    p_list = sub.add_parser("list", help="List chat projects")

    args = parser.parse_args()
    if args.cmd == "log":
        cmd_log(args)
    elif args.cmd == "query":
        cmd_query(args)
    elif args.cmd == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
