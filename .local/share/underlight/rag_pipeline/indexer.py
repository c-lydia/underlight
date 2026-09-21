"""
Route A — indexer.py
Indexes code repos, text, KiCad s-expr files, PDFs, and images (+OCR) into
LanceDB tables. Reads .ragconfig.yaml. Idempotent: safe to re-run.

Run:  python indexer.py [--table projects|downloads|all] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from tqdm import tqdm
from config_loader import load_config

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
cfg = load_config()

# ---------------------------------------------------------------------------
# LanceDB
# ---------------------------------------------------------------------------
try:
    import lancedb
except ImportError:
    print("lancedb not installed — pip install -r requirements.txt")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------
@dataclass
class Embedder:
    model_name: str
    device: str
    batch_size: int
    _model = None

    def __post_init__(self):
        if self.device != "ollama":
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.device == "ollama":
            return self._embed_ollama(texts)
        return self._model.encode(
            texts, batch_size=self.batch_size, convert_to_numpy=True, show_progress_bar=False
        ).tolist()

    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        import requests
        base = cfg["ollama"]["base_url"]
        resp = requests.post(f"{base}/api/embeddings", json={
            "model": cfg["ollama"].get("embed_model", "nomic-embed-text"),
            "prompt": "\n".join(texts),
        }, timeout=120)
        resp.raise_for_status()
        # Ollama returns one vector per request with this endpoint; batch via loop
        vectors = []
        for t in texts:
            r = requests.post(f"{base}/api/embeddings", json={
                "model": cfg["ollama"].get("embed_model", "nomic-embed-text"),
                "prompt": t,
            }, timeout=120)
            r.raise_for_status()
            vectors.append(r.json()["embedding"])
        return vectors


embedder = Embedder(
    model_name=cfg["embedder"]["model"],
    device=cfg["embedder"]["device"],
    batch_size=cfg["embedder"]["batch_size"],
)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
CHUNK_RE_FS = re.compile(r"^\s*(def |class |async def |fn |func |interface |type |struct |enum )\w+")
CHUNK_RE_BLOCK = re.compile(r"^\s*\(")


def chunk_code(text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
    """Split code by function/class defs when possible, else line chunks."""
    lines = text.splitlines()
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if CHUNK_RE_FS.match(line) and current:
            chunks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append(current)

    if not chunks:
        # empty file
        return [text]

    out = []
    for c in chunks:
        s = "\n".join(c)
        if len(s.split()) > max_tokens:
            out.extend(chunk_lines(s.splitlines(), max_tokens, overlap))
        else:
            out.append(s)
    return out


def chunk_lines(lines: list[str], max_tokens: int, overlap: int) -> list[str]:
    out = []
    bucket: list[str] = []
    count = 0
    for line in lines:
        bucket.append(line)
        count += len(line.split())
        if count >= max_tokens:
            out.append("\n".join(bucket))
            # overlap: keep last `overlap` lines in next bucket
            if overlap > 0 and len(bucket) > overlap:
                keep = bucket[-overlap:]
                bucket = keep[:]
                count = sum(len(l.split()) for l in bucket)
            else:
                bucket = []
                count = 0
    if bucket:
        out.append("\n".join(bucket))
    return out


def chunk_text(text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    out = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(p.split()) <= max_tokens:
            out.append(p)
        else:
            out.extend(chunk_lines(p.splitlines(), max_tokens, overlap))
    return out or [text]


def chunk_kicad(text: str) -> list[str]:
    """Split KiCad s-expr by top-level blocks (each (...) group at column 0)."""
    blocks: list[str] = []
    depth = 0
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            current.append(line)
            continue
        # count parens at start of stripped content
        opens = stripped.count("(") - stripped.count(")")
        # rough block split: lines starting with "(" at depth 0 start a new block
        if depth == 0 and stripped.startswith("("):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
        depth += stripped.count("(") - stripped.count(")")
    if current:
        blocks.append("\n".join(current))
    return blocks or [text]


def chunk_pdf_pages(pdf_path: Path) -> list[str]:
    try:
        import fitz  # pymupdf
    except ImportError:
        print("pymupdf not installed for PDF chunking — pip install pymupdf")
        return [f"[PDF: {pdf_path.name} — pymupdf not installed]"]
    doc = fitz.open(str(pdf_path))
    out = []
    for i, page in enumerate(doc):
        txt = page.get_text().strip()
        if txt:
            out.append(f"[PAGE {i+1} of {pdf_path.name}]\n{txt}")
    doc.close()
    return out or [f"[PDF: {pdf_path.name} — no extractable text]"]


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def ocr_image(img_path: Path, langs: list[str], gpu: bool, device: int,
              batch_size: int = 4) -> str:
    """OCR an image; returns text or a short note if nothing found."""
    # EasyOCR for GPU
    if cfg["downloads"]["ocr"]["engine"] == "easyocr" and gpu:
        try:
            import easyocr
        except ImportError:
            print("easyocr not installed — pip install easyocr")
            return f"[OCR SKIPPED: easyocr missing for {img_path.name}]"
        reader = easyocr.Reader(
            langs, gpu=gpu, cuda_device=device, verbose=False,
        )
        results = reader.readtext(str(img_path), batch_size=batch_size)
        texts = [r[1] for r in results if r[1].strip()]
        return "\n".join(texts) if texts else f"[OCR: no text found in {img_path.name}]"
    else:
        # Tesseract CPU fallback
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            print("pytesseract/PIL not installed for Tesseract OCR")
            return f"[OCR SKIPPED: tesseract missing for {img_path.name}]"
        try:
            img = Image.open(str(img_path))
            txt = pytesseract.image_to_string(img, lang=cfg["downloads"]["ocr"]["tesseract"]["lang"])
            return txt.strip() or f"[OCR: no text found in {img_path.name}]"
        except Exception as e:
            return f"[OCR ERROR: {img_path.name}: {e}]"


# ---------------------------------------------------------------------------
# File routing
# ---------------------------------------------------------------------------
def should_index(path: Path, extensions: list[str], exclude_dirs: list[str]) -> bool:
    if not path.is_file():
        return False
    # exclude dirs
    parts = path.parts
    for ex in exclude_dirs:
        if ex in parts:
            return False
    if path.suffix.lower() not in extensions:
        return False
    # size sanity
    mb = path.stat().st_size / (1024 * 1024)
    if mb > 100:
        return False  # skip giant files
    return True


def read_file_text(path: Path, extensions: list[str], cfg: dict) -> list[tuple[str, str]]:
    """Returns list of (chunk, source_desc) tuples."""
    ext = path.suffix.lower()
    chunks: list[tuple[str, str]] = []

    if ext == ".pdf":
        for c in chunk_pdf_pages(path):
            chunks.append((c, f"pdf:{path.name}"))
        return chunks

    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        ocr_cfg = cfg.get("downloads", {}).get("ocr", {})
        if ocr_cfg.get("enabled", False):
            langs = ocr_cfg.get("languages", ["en"])
            gpu = ocr_cfg.get("gpu", False)
            device = ocr_cfg.get("gpu_device", 0)
            bs = ocr_cfg.get("batch_size", 4)
            txt = ocr_image(path, langs, gpu, device, bs)
            chunks.append((txt, f"ocr:{path.name}"))
        else:
            chunks.append((f"[IMAGE: {path.name} — OCR disabled]", f"img:{path.name}"))
        return chunks

    # text-ish files
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        chunks.append((f"[READ ERROR: {path.name}: {e}]", f"err:{path.name}"))
        return chunks

    if ext in {".kicad_pcb", ".kicad_sch", ".kicad_pro", ".kicad_sym", ".kicad_drill", ".kicad_lambda"}:
        for c in chunk_kicad(raw):
            chunks.append((c, f"kicad:{path.name}"))
    elif ext in {".py", ".cpp", ".c", ".h", ".hpp", ".js", ".ts", ".go", ".rs", ".java"}:
        cmax = cfg["chunking"]["code"]["max_tokens"]
        covl = cfg["chunking"]["code"]["overlap_tokens"]
        for c in chunk_code(raw, cmax, covl):
            chunks.append((c, f"code:{path.name}"))
    else:
        tmax = cfg["chunking"]["text"]["max_tokens"]
        tovl = cfg["chunking"]["text"]["overlap_tokens"]
        for c in chunk_text(raw, tmax, tovl):
            chunks.append((c, f"text:{path.name}"))

    return chunks


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------
def make_table_schema():
    import pyarrow as pa
    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("source", pa.string()),
        pa.field("path", pa.string()),
        pa.field("kind", pa.string()),       # code|text|kicad|pdf|ocr|img
        pa.field("project", pa.string()),
        pa.field("embedding", pa.list_(pa.float32(), 384)),  # MiniLM dim
    ])


def upsert_table(db: lancedb.LanceDBConnection, table_name: str, rows: list[dict]):
    schema = make_table_schema()
    try:
        tbl = db.create_table(table_name, schema=schema, exist_ok=True)
    except Exception:
        tbl = db.open_table(table_name)
    if len(rows) == 0:
        return
    import pyarrow as pa
    table = pa.Table.from_pylist(rows, schema=schema)
    tbl.add(table)


def index_dir(root: Path, table_name: str, project_label: str,
              extensions: list[str], exclude_dirs: list[str],
              cfg: dict, dry_run: bool = False) -> int:
    root = root.expanduser().resolve()
    if not root.exists():
        print(f"SKIP: {root} does not exist")
        return 0

    # collect files
    files: list[Path] = []
    for path in root.rglob("*"):
        if should_index(path, extensions, exclude_dirs):
            rel = path.relative_to(root)
            # skip if too big
            if path.stat().st_size / (1024*1024) > 100:
                continue
            files.append(path)

    print(f"Found {len(files)} files to index under {root}")
    if dry_run:
        for f in files:
            print("  DRY:", f)
        return 0

    db = lancedb.connect(cfg["store"]["dir"])
    rows: list[dict] = []
    t0 = time.time()
    processed = 0
    errors = 0

    for path in tqdm(files, desc=f"indexing {root.name}", unit="file"):
        try:
            chunks = read_file_text(path, extensions, cfg)
        except Exception as e:
            errors += 1
            continue
        if not chunks:
            continue
        # batch embed
        texts = [c[0] for c in chunks]
        embs = embedder.embed(texts)
        for (text, src), emb in zip(chunks, embs):
            doc_id = hashlib.sha256(f"{path}|{src}|{text}".encode()).hexdigest()[:16]
            rows.append({
                "id": doc_id,
                "text": text,
                "source": src,
                "path": str(path),
                "kind": src.split(":")[0],
                "project": project_label,
                "embedding": emb,
            })
        processed += 1
        # flush periodically
        if len(rows) >= 2000:
            upsert_table(db, table_name, rows)
            rows = []

    if rows:
        upsert_table(db, table_name, rows)

    elapsed = time.time() - t0
    print(f"Indexed {processed} files, {errors} errors, {len(rows)} final chunks "
          f"→ table '{table_name}' in {elapsed:.1f}s")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Route A indexer")
    parser.add_argument("--table", choices=["projects", "downloads", "home", "all"],
                        default="all", help="which table to index")
    parser.add_argument("--dry-run", action="store_true",
                        help="list files without indexing")
    args = parser.parse_args()

    if args.table in ("projects", "all"):
        index_dir(
            Path(cfg["projects"]["root"]),
            cfg["store"]["tables"]["projects"],
            "projects",
            cfg["projects"]["extensions"],
            cfg["projects"].get("exclude", []),
            cfg,
            dry_run=args.dry_run,
        )

    if args.table in ("downloads", "all"):
        index_dir(
            Path(cfg["downloads"]["root"]),
            cfg["store"]["tables"]["downloads"],
            "downloads",
            cfg["downloads"]["extensions"],
            cfg["downloads"].get("exclude", []),
            cfg,
            dry_run=args.dry_run,
        )

    if args.table in ("home", "all"):
        index_dir(
            Path(cfg["home"]["root"]),
            cfg["store"]["tables"]["home"],
            "home",
            cfg["home"]["extensions"],
            cfg["home"].get("exclude", []),
            cfg,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
