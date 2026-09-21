#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export RAG_CONFIG="${RAG_CONFIG:-$(pwd)/.ragconfig.yaml}"
if [[ ! -f "$RAG_CONFIG" ]]; then
  echo "ERROR: config not found at $RAG_CONFIG" >&2
  exit 1
fi

exec python3 assistant.py "$@"
