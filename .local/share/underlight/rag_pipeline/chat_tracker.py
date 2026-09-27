"""Project-scoped JSONL and vector chat memory for Underlight RAG."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from config_loader import load_config
from rag_core import Embedder, chat_schema, cosine_score, sql_string, table_exists, upsert_rows


cfg = load_config()

_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder(cfg)
    return _embedder


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

    emb = get_embedder().embed([text])[0]
    store_msg(project, entry, emb)
    return entry


def store_msg(project: str, entry: dict, embedding: list[float]):
    import lancedb

    db = lancedb.connect(cfg["store"]["dir"])
    tbl_name = cfg["store"]["tables"]["chat"]
    schema = chat_schema(len(embedding))
    if table_exists(db, tbl_name):
        tbl = db.open_table(tbl_name)
        vector_size = getattr(tbl.schema.field("embedding").type, "list_size", None)
        if vector_size != len(embedding):
            raise RuntimeError(
                f"Chat table has {vector_size}-dimensional vectors, but the embedder returned "
                f"{len(embedding)}. Delete '{tbl_name}' or change back to the original embedder."
            )
        schema = tbl.schema
    else:
        tbl = db.create_table(tbl_name, schema=schema)

    doc_id = "chat_" + hashlib.sha256(
        f"{entry['timestamp']}\0{project}\0{entry['role']}\0{entry['text']}".encode()
    ).hexdigest()[:24]
    upsert_rows(tbl, [{
        "id": doc_id,
        "text": entry["text"],
        "role": entry["role"],
        "project": project,
        "timestamp": entry["timestamp"],
        "metadata": json.dumps(entry.get("metadata", {})),
        "embedding": embedding,
    }], schema)


def rebuild_chat_index() -> int:
    """Re-embed JSONL chat logs after the embedding model changes."""
    import lancedb

    entries: list[dict] = []
    for path in sorted(LOG_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))

    db = lancedb.connect(cfg["store"]["dir"])
    table_name = cfg["store"]["tables"]["chat"]
    if not entries:
        if table_exists(db, table_name):
            db.drop_table(table_name)
        return 0

    batch_size = int(cfg["embedder"].get("batch_size", 64))
    embeddings: list[list[float]] = []
    for start in range(0, len(entries), batch_size):
        embeddings.extend(get_embedder().embed([
            entry["text"] for entry in entries[start:start + batch_size]
        ]))

    rows = []
    for entry, embedding in zip(entries, embeddings):
        project = entry.get("project", cfg["chat"]["default_project"])
        doc_id = "chat_" + hashlib.sha256(
            f"{entry['timestamp']}\0{project}\0{entry['role']}\0{entry['text']}".encode()
        ).hexdigest()[:24]
        rows.append({
            "id": doc_id,
            "text": entry["text"],
            "role": entry["role"],
            "project": project,
            "timestamp": entry["timestamp"],
            "metadata": json.dumps(entry.get("metadata", {})),
            "embedding": embedding,
        })

    if table_exists(db, table_name):
        db.drop_table(table_name)
    schema = chat_schema(len(embeddings[0]))
    table = db.create_table(table_name, schema=schema)
    upsert_rows(table, rows, schema)
    return len(rows)


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
    import lancedb

    db = lancedb.connect(cfg["store"]["dir"])
    tbl_name = cfg["store"]["tables"]["chat"]
    if not table_exists(db, tbl_name):
        return []
    tbl = db.open_table(tbl_name)

    emb = get_embedder().embed([query])[0]
    top_k = min(top_k, cfg["chat"]["retrieval_top_k"])

    search = tbl.search(emb, vector_column_name="embedding").distance_type("cosine")
    if project:
        search = search.where(f"project = {sql_string(project)}")
    results = search.limit(top_k).to_list()
    out = []
    for r in results:
        rec = {
            "text": r["text"],
            "role": r["role"],
            "project": r["project"],
            "timestamp": r["timestamp"],
            "score": cosine_score(r.get("_distance")),
            "metadata": json.loads(r.get("metadata", "{}")),
        }
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


def cmd_rebuild(args):
    count = rebuild_chat_index()
    print(f"Rebuilt chat index from {count} logged messages.")


def main():
    parser = argparse.ArgumentParser(description="Underlight RAG chat tracker")
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
    sub.add_parser("rebuild", help="Re-embed all JSONL chat logs")

    args = parser.parse_args()
    if args.cmd == "log":
        cmd_log(args)
    elif args.cmd == "query":
        cmd_query(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "rebuild":
        cmd_rebuild(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
