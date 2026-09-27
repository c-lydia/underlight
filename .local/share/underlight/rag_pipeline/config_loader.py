"""Load an Underlight RAG config without baking one user's home path into it."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def _expand_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_paths(item) for item in value]
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    return value


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    default = Path(__file__).with_name(".ragconfig.yaml")
    path = Path(config_path or os.environ.get("RAG_CONFIG", default)).expanduser()
    if not path.is_file():
        raise FileNotFoundError(
            f"RAG config not found: {path}. Run 'underlight-rag setup' first."
        )
    with path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError(f"RAG config must contain a mapping: {path}")
    config = _expand_paths(config)
    required = ("embedder", "store", "ollama", "assistant", "chat", "chunking")
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"RAG config is missing sections: {', '.join(missing)}")
    return config
