"""Read-only MCP bridge for the Underlight local RAG index."""

from __future__ import annotations

import json
import sys
from typing import Any

import lancedb

from assistant import ask_ollama, build_prompt, cfg, retrieve
from rag_core import table_names

SUPPORTED_PROTOCOLS = {
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
}
LATEST_PROTOCOL = "2025-11-25"

TOOLS = [
    {
        "name": "search_local_knowledge",
        "description": (
            "Search indexed local files. Cloud clients can receive the returned excerpts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "tables": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "default": None,
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 6,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ask_local_assistant",
        "description": (
            "Retrieve and answer with local Ollama; return only the answer and source metadata."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "tables": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "default": None,
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 6,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "local_rag_status",
        "description": "Show the local RAG models, store, and indexed-table availability.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


def _resolved_tables(tables: list[str] | None) -> list[str]:
    selected = tables or cfg["assistant"]["search_tables"]
    known = set(cfg["store"]["tables"])
    unknown = sorted(set(selected) - known)
    if unknown:
        raise ValueError(
            f"Unknown RAG table(s): {', '.join(unknown)}. "
            f"Choose from: {', '.join(sorted(known))}"
        )
    return list(dict.fromkeys(selected))


def _bounded_top_k(top_k: int) -> int:
    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20")
    return top_k


def search_local_knowledge_impl(
    query: str, tables: list[str] | None = None, top_k: int = 6
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must not be empty")
    selected = _resolved_tables(tables)
    chunks = retrieve(query, selected, top_k=_bounded_top_k(top_k))
    return {
        "query": query,
        "tables": selected,
        "count": len(chunks),
        "results": chunks,
        "privacy": (
            "These local excerpts are now part of the MCP tool result. A cloud-hosted "
            "calling model can receive them."
        ),
    }


def ask_local_assistant_impl(
    query: str, tables: list[str] | None = None, top_k: int = 6
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must not be empty")
    selected = _resolved_tables(tables)
    chunks = retrieve(query, selected, top_k=_bounded_top_k(top_k))
    answer = ask_ollama(
        build_prompt(query, chunks),
        max_context=cfg["ollama"].get("max_context_tokens", 4096),
    )
    return {
        "query": query,
        "answer": answer,
        "local_model": cfg["ollama"]["model"],
        "sources": [
            {
                "path": chunk.get("path", ""),
                "source": chunk.get("source", ""),
                "table": chunk.get("table", ""),
                "score": chunk.get("score", 0),
            }
            for chunk in chunks
        ],
        "privacy": (
            "Retrieval and answer generation ran locally. This answer and source "
            "metadata are visible to the MCP client and its configured model provider."
        ),
    }


def local_rag_status_impl() -> dict[str, Any]:
    db = lancedb.connect(cfg["store"]["dir"])
    configured = cfg["store"]["tables"]
    indexed = set(table_names(db))
    return {
        "embedder": cfg["embedder"]["model"],
        "embedder_device": cfg["embedder"].get("device", "cpu"),
        "local_answer_model": cfg["ollama"]["model"],
        "store": cfg["store"]["dir"],
        "tables": {
            logical: {
                "database_name": physical,
                "indexed": physical in indexed,
            }
            for logical, physical in configured.items()
        },
    }


def _result(request_id: Any, value: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_result(value: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False, indent=2),
            }
        ],
        "isError": is_error,
    }
    if not is_error:
        result["structuredContent"] = value
    return result


def dispatch(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if request_id is None:
        return None
    if method == "initialize":
        requested = params.get("protocolVersion")
        protocol = requested if requested in SUPPORTED_PROTOCOLS else LATEST_PROTOCOL
        return _result(request_id, {
            "protocolVersion": protocol,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "Underlight Local RAG", "version": "1.0.0"},
            "instructions": (
                "Search the local Underlight index for the user's projects and notes. "
                "Prefer ask_local_assistant when raw excerpts should stay local."
            ),
        })
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            if name == "search_local_knowledge":
                value = search_local_knowledge_impl(**arguments)
            elif name == "ask_local_assistant":
                value = ask_local_assistant_impl(**arguments)
            elif name == "local_rag_status":
                value = local_rag_status_impl()
            else:
                return _error(request_id, -32602, f"Unknown tool: {name}")
            return _result(request_id, _tool_result(value))
        except (TypeError, ValueError) as exc:
            return _result(request_id, _tool_result({"error": str(exc)}, is_error=True))
        except Exception as exc:
            print(f"underlight-rag MCP tool failed: {exc}", file=sys.stderr)
            return _result(
                request_id,
                _tool_result({"error": "Local RAG tool execution failed."}, is_error=True),
            )
    return _error(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("request must be a JSON object")
            response = dispatch(message)
        except (json.JSONDecodeError, ValueError) as exc:
            response = _error(None, -32700, f"Parse error: {exc}")
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
