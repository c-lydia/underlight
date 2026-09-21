#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Route A: indexer ==="
echo "Installing deps (first run only)..."
pip install -q -r requirements.txt 2>&1 | tail -3

echo ""
echo "Config loading from .ragconfig.yaml..."
python3 - <<'PY'
import yaml, sys
from pathlib import Path
cfg = yaml.safe_load(Path(".ragconfig.yaml").read_text())
print(f"  projects.root = {cfg['projects']['root']}")
print(f"  downloads.root = {cfg['downloads']['root']}")
print(f"  ollama.base_url = {cfg['ollama']['base_url']}")
print(f"  ollama.model = {cfg['ollama']['model']}")
print(f"  embedder = {cfg['embedder']['model']} ({cfg['embedder']['device']})")
print(f"  store.dir = {cfg['store']['dir']}")
print(f"  ocr.enabled = {cfg['downloads']['ocr']['enabled']} ({cfg['downloads']['ocr']['engine']})")
PY

echo ""
echo "Dry-run: listing files that would be indexed..."
echo "--- projects ---"
python3 indexer.py --table projects --dry-run 2>&1 | head -40
echo ""
echo "--- downloads ---"
python3 indexer.py --table downloads --dry-run 2>&1 | head -40

echo ""
echo "If the file list looks right, run without --dry-run:"
echo "  python3 indexer.py --table projects"
echo "  python3 indexer.py --table downloads"
echo ""
echo "First index will download the embedder model (~80MB) and may take a while."
