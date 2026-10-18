"""
Underlight RAG indexer.
Indexes code repos, text, KiCad s-expr files, PDFs, and images (+OCR) into
LanceDB tables. Reads .ragconfig.yaml. Idempotent: safe to re-run.

Run:  python indexer.py [--table projects|downloads|all] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import fnmatch
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from tqdm import tqdm
from config_loader import load_config
from rag_core import Embedder, document_schema, sql_string, table_exists


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
            # Keep approximately `overlap` words, working backward by line.
            if overlap > 0:
                keep: list[str] = []
                kept_words = 0
                for previous in reversed(bucket):
                    keep.append(previous)
                    kept_words += len(previous.split())
                    if kept_words >= overlap:
                        break
                bucket = list(reversed(keep))
                count = kept_words
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
    import fitz  # pymupdf
    out = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc):
            txt = page.get_text().strip()
            if txt:
                out.append(f"[PAGE {i+1} of {pdf_path.name}]\n{txt}")
    return out or [f"[PDF: {pdf_path.name} — no extractable text]"]


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def ocr_image(img_path: Path, ocr_cfg: dict[str, Any]) -> str:
    """OCR an image; returns text or a short note if nothing found."""
    # EasyOCR for GPU
    langs = ocr_cfg.get("languages", ["en"])
    gpu = bool(ocr_cfg.get("gpu", False))
    if ocr_cfg.get("engine", "tesseract") == "easyocr":
        import easyocr
        reader = easyocr.Reader(
            langs, gpu=gpu, verbose=False,
        )
        results = reader.readtext(str(img_path), batch_size=int(ocr_cfg.get("batch_size", 4)))
        texts = [r[1] for r in results if r[1].strip()]
        return "\n".join(texts) if texts else f"[OCR: no text found in {img_path.name}]"
    else:
        # Tesseract CPU fallback
        import pytesseract
        from PIL import Image
        with Image.open(str(img_path)) as img:
            txt = pytesseract.image_to_string(
                img, lang=ocr_cfg.get("tesseract", {}).get("lang", "eng")
            )
            return txt.strip() or f"[OCR: no text found in {img_path.name}]"


# ---------------------------------------------------------------------------
# File routing
# ---------------------------------------------------------------------------
def should_index(path: Path, root: Path, source_cfg: dict[str, Any]) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    relative = path.relative_to(root)
    includes = source_cfg.get("include", ["*"])
    if includes and not any(relative.match(pattern) or fnmatch.fnmatch(relative.parts[0], pattern)
                            for pattern in includes):
        return False
    for pattern in source_cfg.get("exclude", []):
        if relative.match(pattern) or relative.match(f"**/{pattern}") or any(
            fnmatch.fnmatch(part, pattern) for part in relative.parts
        ):
            return False
    if path.suffix.lower() not in source_cfg["extensions"]:
        return False
    # size sanity
    mb = path.stat().st_size / (1024 * 1024)
    if mb > 100:
        return False  # skip giant files
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        ocr_cfg = source_cfg.get("ocr", {})
        if mb < float(ocr_cfg.get("min_image_mb", 0)):
            return False
        if mb > float(ocr_cfg.get("max_image_mb", 100)):
            return False
    return True


def read_file_text(path: Path, source_cfg: dict[str, Any], cfg: dict[str, Any]) -> list[tuple[str, str]]:
    """Returns list of (chunk, source_desc) tuples."""
    ext = path.suffix.lower()
    chunks: list[tuple[str, str]] = []

    if ext == ".pdf":
        for c in chunk_pdf_pages(path):
            chunks.append((c, f"pdf:{path.name}"))
        return chunks

    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        ocr_cfg = source_cfg.get("ocr", {})
        if ocr_cfg.get("enabled", False):
            txt = ocr_image(path, ocr_cfg)
            chunks.append((txt, f"ocr:{path.name}"))
        else:
            chunks.append((f"[IMAGE: {path.name} — OCR disabled]", f"img:{path.name}"))
        return chunks

    # text-ish files
    raw = path.read_text(encoding="utf-8", errors="replace")

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
def embedding_signature(cfg: dict[str, Any]) -> bytes:
    """Invalidate cached vectors when their configured model/provider changes."""
    settings = dict(cfg["embedder"])
    settings.pop("batch_size", None)
    if settings.get("device") == "ollama":
        settings["ollama_base_url"] = settings.get(
            "ollama_base_url", cfg.get("ollama", {}).get("base_url")
        )
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest().encode()


def _excluded(relative: Path, patterns: list[str]) -> bool:
    return any(
        relative.match(pattern) or relative.match(f"**/{pattern}")
        or any(fnmatch.fnmatch(part, pattern) for part in relative.parts)
        for pattern in patterns
    )


def index_dir(source_cfg: dict[str, Any], table_name: str, project_label: str,
              cfg: dict[str, Any], embedder: Embedder | None = None,
              db: Any = None, dry_run: bool = False, rebuild: bool = False,
              verbose_dry_run: bool = False) -> int:
    root = Path(source_cfg["root"]).expanduser().resolve()
    if not root.exists():
        print(f"SKIP: {root} does not exist")
        return 0
    if not root.is_dir():
        raise ValueError(f"Index source is not a directory: {root}")

    # Unlike rglob, report unreadable directories instead of treating their
    # contents as deleted. Excluded trees are never traversed.
    def scan_error(error):
        raise error

    files = []
    for directory, directories, names in os.walk(root, onerror=scan_error):
        parent = Path(directory)
        directories[:] = [name for name in directories
                          if not (parent / name).is_symlink()
                          and not _excluded((parent / name).relative_to(root), source_cfg.get("exclude", []))]
        for name in names:
            path = parent / name
            if should_index(path, root, source_cfg):
                files.append(path)
    files.sort()
    print(f"Found {len(files)} files to index under {root}")
    if dry_run:
        for path in files if verbose_dry_run else files[:50]:
            print("  DRY:", path)
        if not verbose_dry_run and len(files) > 50:
            print(f"  ... {len(files) - 50} more files; add --verbose to show all")
        return 0
    if db is None or embedder is None:
        raise RuntimeError("index_dir requires a database and embedder when not in dry-run mode")

    import pyarrow as pa

    existing = db.open_table(table_name) if table_exists(db, table_name) else None
    signature = embedding_signature(cfg)
    old_signature = (existing.schema.metadata or {}).get(b"underlight.embedding") if existing else None
    if existing is not None and not rebuild:
        if "generation" not in existing.schema.names:
            raise RuntimeError(f"Table '{table_name}' uses the old schema; rerun with --rebuild.")
        if old_signature is not None and old_signature != signature:
            raise RuntimeError("Embedding configuration changed; rerun with --rebuild to avoid mixing models.")
    cache_enabled = existing is not None and not rebuild and old_signature == signature
    metadata = {b"underlight.embedding": signature}
    if (existing is not None and not rebuild and old_signature is None
            and existing.count_rows(f"project != {sql_string(project_label)}")):
        # Do not certify the model of legacy rows belonging to another source.
        metadata = {}
    original_version = existing.version if existing is not None else None
    generation = uuid.uuid4().hex
    batch_size = max(1, int(cfg["embedder"].get("batch_size", 64)))
    pending = []
    seen_ids = set()
    errors = []
    chunk_count = reused = duplicates = 0
    started = time.monotonic()

    # Stage the complete replacement on disk. No live table is changed until
    # all reads and embeddings succeed. LanceDB overwrite commits a new version
    # rather than dropping the previous table before work starts.
    with tempfile.TemporaryFile() as spool:
        writer = None
        schema = None

        def stage(rows):
            nonlocal writer, schema
            if not rows:
                return
            dimension = len(rows[0]["embedding"])
            if dimension == 0 or any(len(row["embedding"]) != dimension for row in rows):
                raise RuntimeError("Embedder returned empty or inconsistent vectors")
            if schema is None:
                if existing is not None and not rebuild:
                    old_dimension = existing.schema.field("embedding").type.list_size
                    if old_dimension != dimension and existing.count_rows() > 0:
                        raise RuntimeError("Embedding dimension changed; rerun with --rebuild.")
                schema = document_schema(dimension).with_metadata(metadata)
                writer = pa.ipc.new_file(spool, schema)
            writer.write_table(pa.Table.from_pylist(rows, schema=schema))

        def flush():
            if not pending:
                return
            vectors = embedder.embed([item["text"] for item in pending])
            if len(vectors) != len(pending):
                raise RuntimeError(f"Embedder returned {len(vectors)} vectors for {len(pending)} chunks")
            stage([dict(item, embedding=vector) for item, vector in zip(pending, vectors)])
            pending.clear()

        try:
            for path in tqdm(files, desc=f"indexing {root.name}", unit="file"):
                try:
                    chunks = read_file_text(path, source_cfg, cfg)
                except Exception as exc:
                    errors.append(path)
                    tqdm.write(f"WARN: failed to read {path}: {exc}")
                    continue
                cached = {}
                if cache_enabled:
                    cached = {row["id"]: row["embedding"] for row in
                              existing.search().where(
                                  f"project = {sql_string(project_label)} AND path = {sql_string(str(path))}"
                              ).select(["id", "embedding"]).limit(None).to_list()}
                for text, src in chunks:
                    doc_id = hashlib.sha256(f"{path}|{src}|{text}".encode()).hexdigest()[:16]
                    if doc_id in seen_ids:
                        duplicates += 1
                        continue
                    seen_ids.add(doc_id)
                    item = dict(id=doc_id, text=text, source=src, path=str(path),
                                kind=src.split(":")[0], project=project_label, generation=generation)
                    if doc_id in cached:
                        stage([dict(item, embedding=cached[doc_id])])
                        reused += 1
                    else:
                        pending.append(item)
                    chunk_count += 1
                    if len(pending) >= batch_size:
                        flush()
            if errors:
                raise RuntimeError(f"Index update aborted: {len(errors)} files failed; previous index preserved.")
            flush()
            # A normal update must not remove other sources sharing this table.
            if existing is not None and not rebuild:
                for batch in existing.search().where(
                    f"project != {sql_string(project_label)}"
                ).limit(None).to_batches(batch_size=1024):
                    stage(batch.to_pylist())
            if writer is None and existing is not None:
                schema = existing.schema.with_metadata(metadata)
                writer = pa.ipc.new_file(spool, schema)
        finally:
            if writer is not None:
                writer.close()

        if schema is not None:
            if existing is not None and db.open_table(table_name).version != original_version:
                raise RuntimeError("Index changed during this run; previous index preserved. Retry the update.")
            spool.seek(0)
            staged = pa.ipc.open_file(spool)
            batches = pa.RecordBatchReader.from_batches(
                schema, (staged.get_batch(i) for i in range(staged.num_record_batches))
            )
            db.create_table(table_name, data=batches, schema=schema,
                            mode="overwrite" if existing is not None else "create")
    print(f"Indexed {len(files)} files, {chunk_count} unique chunks ({reused} cached) "
          f"→ table '{table_name}' in {time.monotonic() - started:.1f}s")
    if duplicates:
        print(f"Skipped {duplicates} duplicate chunks with identical source text.")
    return chunk_count


def main():
    parser = argparse.ArgumentParser(description="Underlight local RAG indexer")
    parser.add_argument("--table", choices=["projects", "downloads", "home", "all"],
                        default="all", help="which table to index")
    parser.add_argument("--dry-run", action="store_true",
                        help="list files without indexing")
    parser.add_argument("--rebuild", action="store_true",
                        help="build a fresh index and replace the old table only after success")
    parser.add_argument("--verbose", action="store_true",
                        help="show every matching file during a dry run")
    args = parser.parse_args()

    cfg = load_config()
    embedder = None
    db = None
    if not args.dry_run:
        import lancedb

        embedder = Embedder(cfg)
        db = lancedb.connect(cfg["store"]["dir"])

    if args.table in ("projects", "all"):
        index_dir(cfg["projects"], cfg["store"]["tables"]["projects"], "projects",
                  cfg, embedder, db, args.dry_run, args.rebuild, args.verbose)

    if args.table in ("downloads", "all"):
        index_dir(cfg["downloads"], cfg["store"]["tables"]["downloads"], "downloads",
                  cfg, embedder, db, args.dry_run, args.rebuild, args.verbose)

    if args.table in ("home", "all"):
        index_dir(cfg["home"], cfg["store"]["tables"]["home"], "home",
                  cfg, embedder, db, args.dry_run, args.rebuild, args.verbose)


if __name__ == "__main__":
    main()
