# Route A — RAG / Knowledge Injection Pipeline

Local AI assistant that remembers your projects, code, KiCad designs, conversations, and files — grounded in what's actually on your machine, not in the model's training data.

Designed for a local Linux workstation with:
- Ollama + `qwen3:4b` (RTX 3050, 4GB VRAM)
- Code repos in `~/projects/`
- Downloaded files in `~/Downloads/` (PDFs, images with OCR)
- Fresh chat tracker for project conversations

## What it does

**Index** your stuff into a vector store (LanceDB, file-based, no server):
- Code files split by function/class boundaries
- KiCad `.kicad_pcb` / `.kicad_sch` / `.kicad_pro` split by s-expression blocks
- PDFs chunked per page
- Images OCR'd via EasyOCR (CUDA on RTX 3050) or Tesseract (CPU fallback)

**Retrieve** relevant chunks when you ask a question — searches code, downloads, and past conversations in one query.

**Answer** via Ollama `qwen3:4b` with the retrieved context in the prompt.

**Remember** conversations — every assistant exchange can be logged to a JSONL chat log and embedded for future retrieval.

## What it doesn't do (yet)

- Drawing/painting style learning → that's Route B (LoRA fine-tune)
- Singing/music advice → that's a plugin, not RAG; slot it in later
- Live image viewing — images get OCR'd for text content; pure art images get a metadata record only

## Quick start

```bash
# 1. Copy this dir to your host
scp -r rag_pipeline/ ~/projects/rag_pipeline/
cd ~/projects/rag_pipeline/

# 2. Edit .ragconfig.yaml — set projects.root, downloads.root, ollama.base_url
vim .ragconfig.yaml

# 3. Install deps
pip install -r requirements.txt

# 4. Verify setup
bash verify_host.sh

# 5. Index your code repos (first run downloads embedder model ~80MB)
python indexer.py --table projects

# 6. Index Downloads + OCR (optional, slower)
python indexer.py --table downloads

# 7. Try the assistant
bash run_assistant.sh answer "how do I route a differential pair in kicad"

# 8. Start the HTTP API (optional — for Hermes or other tools)
bash run_server.sh
# → POST http://localhost:8080/ask  {"query":"..."}
# → GET  http://localhost:8080/health
```

## Architecture

```
.ragconfig.yaml          ← all paths, model choices, chunking params
├── indexer.py           ← indexes files into LanceDB tables
├── chat_tracker.py      ← JSONL chat log + embed + retrieve past threads
├── assistant.py         ← CLI: query → retrieve → Ollama → answer
├── rag_server.py        ← HTTP API wrapper for the assistant
└── run_*.sh             ← thin shells that set RAG_CONFIG and exec python

LanceDB store (~/.rag_store/)
├── idx_projects         ← code + kicad + text chunks
├── idx_downloads        ← downloads + OCR'd images
└── idx_chat             ← past conversation messages
```

### Data flow

```
query → embed (MiniLM L6, CPU) → search LanceDB tables → top-K chunks
     → build prompt (system + context + history + question)
     → Ollama qwen3:4b (q4_K_M, ~2.3GB VRAM on RTX 3050)
     → answer → optionally log to chat tracker
```

### Why these choices

| Decision | Reason |
|---|---|
| LanceDB over Chroma/Weaviate | File-based, no server, handles GB scale, queries fast, survives reboots |
| `all-MiniLM-L6-v2` embedder on CPU | ~80MB, fast, leaves VRAM for qwen. Ollama embed models are an option too (see config comment) |
| Code chunking by `def`/`class` boundary | Semantic units, not arbitrary line breaks. Falls back to line-chunking for big functions |
| KiCad chunked by s-expr blocks | KiCad files are s-expressions — top-level `(...)` blocks are meaningful units (components, tracks, layers) |
| EasyOCR with CUDA for images | RTX 3050 can handle it; throttle batch_size so qwen keeps VRAM. Tesseract as CPU fallback |
| `qwen3:4b` at q4_K_M | Fits in ~2.3GB VRAM on a 4GB card with headroom for embeddings/OCR spikes |
| Chat tracker as JSONL + LanceDB | Simple, queryable, survives restarts. Separate from Hermes logs — fresh project-scoped tracker |

## Config reference (`.ragconfig.yaml`)

### `projects` / `downloads`

```yaml
projects:
  root: $HOME/projects                  # ← EDIT
  include: ["*"]                         # globs relative to root
  exclude: ["node_modules", ".git", ...] # dirs to skip
  extensions: [...]                      # file suffixes to index
```

Set `downloads.ocr.enabled: false` to skip the slow OCR pass on first run and add it later.

### `chunking`

- `code.max_tokens` / `text.max_tokens` — fallback chunk size when boundary splitting isn't possible
- `kicad.strategy: "block"` — split KiCad s-expr by top-level blocks

### `embedder`

```yaml
embedder:
  model: "sentence-transformers/all-MiniLM-L6-v2"
  device: "cpu"          # leave on CPU to save VRAM for qwen
  batch_size: 64
```

To use an Ollama embed model instead (keeps everything in Ollama):
```yaml
embedder:
  model: "nomic-embed-text"
  device: "ollama"
  ollama_base_url: "http://localhost:11434"
```

### `ollama`

```yaml
ollama:
  base_url: "http://localhost:11434"
  model: "qwen3:4b"      # pulled quant: q4_K_M for 4GB VRAM
  timeout_s: 120
  retrieval:
    top_k: 6             # chunks per query
    min_score: 0.25      # drop low-confidence chunks
```

### `chat`

```yaml
chat:
  log_dir: $HOME/.local/state/underlight/rag-chatlogs
  default_project: "default"
  auto_log: true         # log every assistant.run exchange
  retrieval_top_k: 8     # past messages to fetch per query
```

### `assistant`

```yaml
assistant:
  search_tables: ["idx_projects", "idx_downloads", "idx_chat"]
  verbose: false         # print retrieved chunks to stderr
```

## Usage

### Assistant CLI

```bash
# Basic query with retrieval
bash run_assistant.sh answer "explain the pcb routing for the lora board"

# With chat history + auto-log
bash run_assistant.sh answer "what did we decide about the stackup" --remember

# Search only specific tables
bash run_assistant.sh answer "find the uart driver" --tables idx_projects

# Verbose: see what chunks were retrieved
bash run_assistant.sh answer "why is the kicad netlist wrong" --verbose

# Direct Ollama query (no retrieval) — for testing
bash run_assistant.sh ask "what model are you"
```

### Chat tracker

```bash
# Log a message manually
bash run_chat.sh log --role user --text "we should use 4-layer for the lora board"
bash run_chat.sh log --role assistant --text "4-layer 1.6mm FR4, GPIO on layer 2"

# Query past conversations
bash run_chat.sh query "what did we decide about the stackup"

# List projects
bash run_chat.sh list
```

### HTTP API (optional)

```bash
bash run_server.sh
# → listening on http://localhost:8080

# Query
curl -s -X POST http://localhost:8080/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"how do I route a diff pair in kicad","remember":true}' | python3 -m json.tool

# Log a message
curl -s -X POST http://localhost:8080/log \
  -H 'Content-Type: application/json' \
  -d '{"project":"default","role":"user","text":"trying to route diffpair on lora board"}'

# Health
curl http://localhost:8080/health | python3 -m json.tool
```

## Re-indexing

Safe to re-run — LanceDB upserts by document ID (hash of content + source):
```bash
python indexer.py --table projects    # re-index code
python indexer.py --table downloads   # re-index downloads
```

To wipe a table and start fresh:
```python
import lancedb
db = lancedb.connect("~/.local/share/underlight/rag-store")
db.drop_table("idx_projects")   # or idx_downloads, idx_chat
```

## GPU notes (RTX 3050, 4GB)

- qwen3:4b runs at q4_K_M → ~2.3GB VRAM. Leaves ~1.7GB for spikes.
- EasyOCR CUDA uses GPU temporarily — batch_size=4 keeps it modest.
- Embedding runs on CPU (MiniLM L6) — no VRAM cost.
- If you see Ollama OOM, reduce `ollama.retrieval.top_k` or close other GPU apps.

## Routes B and C (future)

- **Route B**: LoRA fine-tune qwen3:4b on your style + domain knowledge, reload into Ollama. Pushed until Route A proves useful.
- **Route C**: Feedback loop — collect preference data from your corrections/accepts, use it to improve retrieval or fine-tune.

## Status

Initial implementation. Not yet run on the host — files are written in this container, ready to copy over and execute.

Known gaps to fill on first host run:
- Verify Ollama `qwen3:4b` is pulled (run `ollama pull qwen3:4b` if not)
- Test OCR on a few images before committing to a full Downloads pass
- Tune `chunking.max_tokens` and `retrieval.top_k` based on real query results
- Add `tree-sitter` code chunking for deeper semantic splits (currently regex-based `def`/`class` boundary detection)
