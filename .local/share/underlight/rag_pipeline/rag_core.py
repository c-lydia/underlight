"""Shared lazy embedding and LanceDB helpers for Underlight RAG."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def table_names(db: Any) -> list[str]:
    """Normalize LanceDB's table-list result across supported releases."""
    result = db.list_tables()
    if hasattr(result, "tables"):
        result = result.tables
    names: list[str] = []
    for item in result:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, tuple) and item:
            names.append(str(item[0]))
    return names


def table_exists(db: Any, name: str) -> bool:
    return name in table_names(db)


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def cosine_score(distance: float | None) -> float:
    return max(-1.0, min(1.0, 1.0 - float(distance if distance is not None else 1.0)))


@dataclass
class Embedder:
    """Embedding adapter that does not load a model until the first query."""

    config: dict[str, Any]
    _model: Any = field(default=None, init=False, repr=False)

    @property
    def settings(self) -> dict[str, Any]:
        return self.config["embedder"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.settings.get("device", "cpu") == "ollama":
            return self._embed_ollama(texts)
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self.settings["model"], device=self.settings.get("device", "cpu")
            )
        vectors = self._model.encode(
            texts,
            batch_size=int(self.settings.get("batch_size", 64)),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        import requests

        base = self.settings.get("ollama_base_url", self.config["ollama"]["base_url"])
        model = self.settings["model"]
        timeout = int(self.config["ollama"].get("timeout_s", 120))
        response = requests.post(
            f"{base.rstrip('/')}/api/embed",
            json={"model": model, "input": texts},
            timeout=timeout,
        )
        if response.status_code != 404:
            response.raise_for_status()
            vectors = response.json().get("embeddings")
            if vectors:
                return vectors

        vectors: list[list[float]] = []
        for text in texts:
            fallback = requests.post(
                f"{base.rstrip('/')}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=timeout,
            )
            fallback.raise_for_status()
            vectors.append(fallback.json()["embedding"])
        return vectors


def document_schema(dimension: int):
    import pyarrow as pa

    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("source", pa.string()),
        pa.field("path", pa.string()),
        pa.field("kind", pa.string()),
        pa.field("project", pa.string()),
        pa.field("generation", pa.string()),
        pa.field("embedding", pa.list_(pa.float32(), dimension)),
    ])


def chat_schema(dimension: int):
    import pyarrow as pa

    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("role", pa.string()),
        pa.field("project", pa.string()),
        pa.field("timestamp", pa.string()),
        pa.field("metadata", pa.string()),
        pa.field("embedding", pa.list_(pa.float32(), dimension)),
    ])


def upsert_rows(table: Any, rows: list[dict[str, Any]], schema: Any) -> None:
    if not rows:
        return
    import pyarrow as pa

    # LanceDB rejects a merge batch when multiple source rows share one key.
    # Keep the final row for each ID as a defensive boundary check.
    unique_rows = list({row["id"]: row for row in rows}.values())
    data = pa.Table.from_pylist(unique_rows, schema=schema)
    table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(data)
