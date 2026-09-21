#!/usr/bin/env bash
set -euo pipefail

# Verify Route A setup from the Ubuntu 26 host.
# Run this AFTER copying rag_pipeline/ to your host and editing .ragconfig.yaml.

cd "$(dirname "$0")"

echo "=== 1. Config check ==="
if [[ ! -f .ragconfig.yaml ]]; then
  echo "FAIL: .ragconfig.yaml missing — copy it from the repo and edit paths." >&2
  exit 1
fi

python3 - <<'PY'
import yaml, sys
from pathlib import Path
cfg = yaml.safe_load(Path(".ragconfig.yaml").read_text())
errors = []
for key in ["projects.root", "downloads.root", "ollama.base_url"]:
    parts = key.split(".")
    val = cfg
    for p in parts:
        val = val.get(p) if isinstance(val, dict) else None
    if not val:
        errors.append(f"missing config: {key}")
if errors:
    for e in errors:
        print(f"  FAIL: {e}")
    sys.exit(1)
print("  projects.root    =", cfg["projects"]["root"])
print("  downloads.root   =", cfg["downloads"]["root"])
print("  ollama.base_url  =", cfg["ollama"]["base_url"])
print("  ollama.model     =", cfg["ollama"]["model"])
print("  embedder         =", cfg["embedder"]["model"])
print("  store.dir        =", cfg["store"]["dir"])
print("  OK")
PY

echo ""
echo "=== 2. Ollama reachability ==="
OLLAMA_URL=$(python3 -c "import yaml; print(yaml.safe_load(open('.ragconfig.yaml'))['ollama']['base_url'])")
curl -s -m 5 "$OLLAMA_URL/api/tags" >/dev/null 2>&1 && echo "  Ollama reachable at $OLLAMA_URL" || {
  echo "  FAIL: cannot reach Ollama at $OLLAMA_URL"
  echo "  Is Ollama running on the host? Try: ollama serve"
  exit 1
}
MODEL=$(python3 -c "import yaml; print(yaml.safe_load(open('.ragconfig.yaml'))['ollama']['model'])")
curl -s -m 5 -X POST "$OLLAMA_URL/api/generate" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"Reply with exactly: OLLAMA_READY\",\"stream\":false,\"options\":{\"num_ctx\":256}}" \
  2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('  Model', d.get('model','?'), 'responds:', d.get('response','?')[:40])" 2>/dev/null || {
  echo "  WARN: model $MODEL may not be pulled. Run: ollama pull $MODEL"
}

echo ""
echo "=== 3. Python deps check ==="
missing=0
for pkg in sentence_transformers lancedb yaml PIL easyocr cv2 requests tqdm fitz; do
  python3 -c "import $pkg" 2>/dev/null && echo "  $pkg: OK" || { echo "  $pkg: MISSING — pip install -r requirements.txt"; missing=1; }
done
if [[ $missing -eq 1 ]]; then
  echo "  Install with: pip install -r requirements.txt"
fi

echo ""
echo "=== 4. GPU check (for OCR) ==="
if python3 -c "import easyocr; print('  easyocr available')" 2>/dev/null; then
  python3 - <<'PY' 2>/dev/null && echo "  EasyOCR CUDA will use GPU" || echo "  EasyOCR available but CUDA not detected — OCR will use CPU"
import easyocr
reader = easyocr.Reader(['en'], gpu=True, verbose=False)
print('  GPU device:', reader.device)
PY
else
  echo "  easyocr not installed — OCR will be skipped unless you install it."
fi

echo ""
echo "=== 5. Disk space for store ==="
STORE=$(python3 -c "import yaml; print(yaml.safe_load(open('.ragconfig.yaml'))['store']['dir'])")
STORE_PARENT=$(dirname "$STORE")
if df -h "$STORE_PARENT" 2>/dev/null | tail -1 | grep -qE "[0-9]+G"; then
  echo "  store dir parent ($STORE_PARENT) has space"
else
  echo "  WARN: cannot check space for $STORE_PARENT"
fi

echo ""
echo "=== Setup looks good. Next steps: ==="
echo "  1. python3 indexer.py --table projects      # index code repos"
echo "  2. python3 indexer.py --table downloads     # index Downloads (+OCR)"
echo "  3. ./run_assistant.sh answer 'test query'   # try the assistant"
echo "  4. ./run_server.sh &                        # start HTTP API (optional)"
