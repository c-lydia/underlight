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
import re
import time
import uuid
from pathlib import Path
from typing import Any

from tqdm import tqdm
from config_loader import load_config
from rag_core import Embedder, document_schema, sql_string, table_exists, upsert_rows


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
def ocr_image(img_path: Path, ocr_cfg: dict[str, Any]) -> str:
    """OCR an image; returns text or a short note if nothing found."""
    # EasyOCR for GPU
    langs = ocr_cfg.get("languages", ["en"])
    gpu = bool(ocr_cfg.get("gpu", False))
    if ocr_cfg.get("engine", "tesseract") == "easyocr":
        try:
            import easyocr
        except ImportError:
            print("easyocr not installed — pip install easyocr")
            return f"[OCR SKIPPED: easyocr missing for {img_path.name}]"
        reader = easyocr.Reader(
            langs, gpu=gpu, verbose=False,
        )
        results = reader.readtext(str(img_path), batch_size=int(ocr_cfg.get("batch_size", 4)))
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
            txt = pytesseract.image_to_string(
                img, lang=ocr_cfg.get("tesseract", {}).get("lang", "eng")
            )
            return txt.strip() or f"[OCR: no text found in {img_path.name}]"
        except Exception as e:
            return f"[OCR ERROR: {img_path.name}: {e}]"


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
def _open_table(db: Any, table_name: str, dimension: int, rebuild: bool = False):
    if rebuild and table_exists(db, table_name):
        db.drop_table(table_name)
    if table_exists(db, table_name):
        table = db.open_table(table_name)
        fields = {field.name: field for field in table.schema}
        if "generation" not in fields:
            raise RuntimeError(
                f"Table '{table_name}' uses the old schema; rerun with --rebuild."
            )
        vector_size = getattr(fields["embedding"].type, "list_size", None)
        if vector_size != dimension:
            raise RuntimeError(
                f"Table '{table_name}' has {vector_size}-dimensional vectors, but the "
                f"configured embedder returned {dimension}; rerun with --rebuild."
            )
        return table, table.schema
    schema = document_schema(dimension)
    return db.create_table(table_name, schema=schema), schema


def index_dir(source_cfg: dict[str, Any], table_name: str, project_label: str,
              cfg: dict[str, Any], embedder: Embedder | None = None,
              db: Any = None, dry_run: bool = False, rebuild: bool = False,
              verbose_dry_run: bool = False) -> int:
    root = Path(source_cfg["root"])
    root = root.expanduser().resolve()
    if not root.exists():
        print(f"SKIP: {root} does not exist")
        return 0

    # collect files
    files: list[Path] = []
    for path in root.rglob("*"):
        if should_index(path, root, source_cfg):
            files.append(path)

    print(f"Found {len(files)} files to index under {root}")
    if dry_run:
        shown = files if verbose_dry_run else files[:50]
        for f in shown:
            print("  DRY:", f)
        if len(shown) < len(files):
            print(f"  ... {len(files) - len(shown)} more files; add --verbose to show all")
        return 0

    if db is None or embedder is None:
        raise RuntimeError("index_dir requires a database and embedder when not in dry-run mode")
    if rebuild and table_exists(db, table_name):
        db.drop_table(table_name)
        rebuild = False
    pending: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    table = None
    schema = None
    generation = uuid.uuid4().hex
    t0 = time.time()
    processed = 0
    errors = 0
    chunk_count = 0
    duplicate_count = 0
    seen_ids: set[str] = set()
    embed_batch_size = max(1, int(cfg["embedder"].get("batch_size", 64)))

    def flush_embeddings() -> None:
        nonlocal table, schema, rebuild, chunk_count, rows
        if not pending:
            return
        embeddings = embedder.embed([item["text"] for item in pending])
        if len(embeddings) != len(pending):
            raise RuntimeError(
                f"Embedder returned {len(embeddings)} vectors for {len(pending)} chunks"
            )
        for item, embedding in zip(pending, embeddings):
            item["embedding"] = embedding
            rows.append(item)
            chunk_count += 1
        pending.clear()
        if len(rows) >= 2000:
            if table is None:
                table, schema = _open_table(
                    db, table_name, len(rows[0]["embedding"]), rebuild
                )
                rebuild = False
            upsert_rows(table, rows, schema)
            rows = []

    for path in tqdm(files, desc=f"indexing {root.name}", unit="file"):
        try:
            chunks = read_file_text(path, source_cfg, cfg)
        except Exception as exc:
            errors += 1
            tqdm.write(f"WARN: failed to read {path}: {exc}")
            continue
        if not chunks:
            continue
        for text, src in chunks:
            doc_id = hashlib.sha256(f"{path}|{src}|{text}".encode()).hexdigest()[:16]
            if doc_id in seen_ids:
                duplicate_count += 1
                continue
            seen_ids.add(doc_id)
            pending.append({
                "id": doc_id,
                "text": text,
                "source": src,
                "path": str(path),
                "kind": src.split(":")[0],
                "project": project_label,
                "generation": generation,
            })
            if len(pending) >= embed_batch_size:
                flush_embeddings()
        processed += 1

    flush_embeddings()
    if rows:
        if table is None:
            table, schema = _open_table(db, table_name, len(rows[0]["embedding"]), rebuild)
        upsert_rows(table, rows, schema)

    if table is None and table_exists(db, table_name):
        table = db.open_table(table_name)
        if "generation" not in table.schema.names:
            raise RuntimeError(f"Table '{table_name}' uses the old schema; rerun with --rebuild.")
    if table is not None and errors == 0:
        table.delete(
            f"project = {sql_string(project_label)} AND generation != {sql_string(generation)}"
        )
    elif errors:
        print("Preserving previous-generation chunks because one or more files failed.")

    elapsed = time.time() - t0
    print(f"Indexed {processed} files, {errors} errors, {chunk_count} unique chunks "
          f"→ table '{table_name}' in {elapsed:.1f}s")
    if duplicate_count:
        print(f"Skipped {duplicate_count} duplicate chunks with identical source text.")
    return chunk_count


def main():
    parser = argparse.ArgumentParser(description="Underlight local RAG indexer")
    parser.add_argument("--table", choices=["projects", "downloads", "home", "all"],
                        default="all", help="which table to index")
    parser.add_argument("--dry-run", action="store_true",
                        help="list files without indexing")
    parser.add_argument("--rebuild", action="store_true",
                        help="replace incompatible/old tables before indexing")
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
