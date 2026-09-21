#!/usr/bin/env bash
# OpenCode runner for Route A — delegates heavy implementation to OpenCode
# while you stay in the loop.
#
# Usage:
#   ./run_opencode.sh run 'Add retry logic to the Ollama call in assistant.py'
#   ./run_opencode.sh run 'Review indexer.py for chunking bugs' -f indexer.py
#   ./run_opencode.sh session                    # interactive TUI (background)
#
# Environment:
#   RAG_CONFIG  — path to .ragconfig.yaml (default: ./rag_pipeline/.ragconfig.yaml)
#   OPENCODE_MODEL — force a model, e.g. openrouter/anthropic/claude-sonnet-4

set -euo pipefail
cd "$(dirname "$0")"

OPENCODE_BIN="$(which opencode 2>/dev/null || echo "")"
if [[ -z "$OPENCODE_BIN" ]]; then
  echo "OpenCode not found. Install: npm i -g opencode-ai@latest" >&2
  echo "Then: opencode auth login" >&2
  exit 1
fi

export RAG_CONFIG="${RAG_CONFIG:-$(pwd)/.ragconfig.yaml}"
if [[ ! -f "$RAG_CONFIG" ]]; then
  echo "ERROR: config not found at $RAG_CONFIG" >&2
  exit 1
fi

# Passed through to opencode
exec "$OPENCODE_BIN" "$@"
