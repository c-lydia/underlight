# Route A — Design Notes

Dense notes for the person implementing/fixing this. Not a user doc — see README.md.

## Why LanceDB

- File-based, no server process. Store is a directory: `~/.rag_store/`.
- Upserts by document ID — re-running indexer is idempotent.
- `search(vector).limit(N)` returns distance; we convert to a 0–1 score: `score = 1.0 - distance`.
- Schema: `id, text, source, path, kind, project, embedding` (384-dim MiniLM).
- One table per source (projects / downloads / chat) so each can be re-indexed independently.

## Chunking details

### Code
Regex matches lines starting with `def `, `class `, `async def `, `fn `, `func `, `interface `, `type `, `struct `, `enum ` — when a new def starts and we have accumulated lines, flush the current chunk and start a new one.

Fallback: if a def-boundary chunk exceeds `max_tokens` (512), split it by lines into `max_tokens`-sized buckets with `overlap_tokens` (64) carryover.

### KiCad s-expressions
KiCad `.kicad_pcb`, `.kicad_sch`, `.kicad_pro` etc. are s-expressions. We split on top-level `(` lines when depth is 0 — rough but works for component blocks, track lists, layer definitions. Not perfect for deeply nested structures; tree-sitter would be better but isn't installed by default.

### PDF
One chunk per page via `pymupdf` (`fitz`). Each chunk prefixed with `[PAGE N of filename]`. Pages with no extractable text → a note chunk.

### Images
If `downloads.ocr.enabled: true`:
- EasyOCR on CUDA (RTX 3050): `easyocr.Reader(langs, gpu=True, cuda_device=0)`. Reads text from the image.
- Tesseract CPU fallback: `pytesseract.image_to_string`.
- If OCR finds nothing → `[OCR: no text found in filename]`.
- If OCR disabled → `[IMAGE: filename — OCR disabled]` (metadata-only record).

Min/max image size filters skip noise (tiny icons, huge raw renders).

### Text (markdown, JSON, YAML, etc.)
Split by paragraph (`\n\s*\n`), chunk paragraphs over `max_tokens` by lines.

## Embedder

CPU: `sentence-transformers/all-MiniLM-L6-v2`, 384-dim, ~80MB, fast on CPU.

Ollama alternative (commented in config):
```yaml
embedder:
  model: "nomic-embed-text"
  device: "ollama"
```
The indexer's `Embedder` class handles both — `device: "ollama"` hits `/api/embeddings` per text. Slower for bulk indexing but keeps everything in Ollama.

## Ollama call

`POST /api/generate` with `stream: false`. Options:
```json
{
  "num_ctx": 4096,
  "temperature": 0.4,
  "top_p": 0.9
}
```

Errors:
- Timeout → "Ollama timed out after N s. Model may be loading."
- ConnectionError → "Cannot reach Ollama at <url>. Is it running?"
- Other → returned as `[ERROR: ...]`

Model: `qwen3:4b` (q4_K_M by default on 4GB VRAM).

## Prompt structure

```
[system prompt]
You are a practical AI assistant helping a developer/designer who works with code,
KiCad PCB design, digital art, and singing/music. Use the retrieved context below to
ground your answers. If the context doesn't have the answer, say so and suggest what
to check. Prefer concrete steps, commands, and file paths over vague advice.

## Retrieved context
1. (score=0.87, code:[main.py] (/home/.../main.py))
   def run_board():
       ...

2. (score=0.72, kicad:[board.kicad_pcb])
   (module ...

## Past conversation
USER: what did we decide about the stackup?
ASSISTANT: 4-layer 1.6mm FR4...

## User question
how do I route a differential pair in kicad?

## Answer
```

## Chat tracker

- JSONL log per project: `~/.rag_chatlogs/<project>.jsonl`.
- Each message: `{timestamp, project, role, text, metadata}`.
- Each message also upserted into `idx_chat` LanceDB table with embedding.
- `query_chat(query, top_k, project)` → similarity search on `idx_chat`.
- `assistant.py --remember` fetches past messages and logs the new exchange.

## Retrieval

Multi-table: search each configured table, collect chunks, filter by `min_score`, sort by score, take `top_k`.

Default tables: `idx_projects`, `idx_downloads`, `idx_chat`.

## File indexer idempotency

Document ID = `sha256(path|source|text)[:16]`. Same content → same ID → LanceDB upsert replaces it. Re-running the indexer is safe.

## Docker / container note

This code runs on the Linux host rather than inside an isolated AI sandbox.
Review the RAG config paths, install the requirements in an isolated virtual
environment, and then run the indexer.

## OpenCode integration

OpenCode is available as an autonomous coding worker for heavy implementation tasks (refactoring, writing tests, building features). The skill is at `autonomous-ai-agents/opencode`. Use `opencode run '...'` for one-shot tasks, or `opencode` with `background=true, pty=true` for interactive sessions.

Not wired into the RAG pipeline yet — future: assistant could delegate code tasks to OpenCode via the HTTP API.

## Future gaps

- tree-sitter-based code chunking (deeper semantic splits than regex def-boundary)
- OCR language options beyond English (add "th" if reading Thai docs)
- Image metadata extraction (dimensions, format) for art files
- PDF table/figure detection (currently page-level only)
- Query rewriting / hybrid search (keyword + vector)
- Rate limiting / request queue for the HTTP server
- Authentication on the HTTP API (currently open)
