import hashlib
import re
from pathlib import Path
from typing import Dict, List, Tuple

import chromadb
import pdfplumber
from sentence_transformers import SentenceTransformer

from backend.config import appSettings


settings = appSettings()

DEFAULT_INPUT_DIR = Path("data/rag/raw_pdfs")


def clean_text(text: str) -> str:
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    if not text:
        return []

    if overlap >= chunk_size:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")

    chunks: List[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            window_start = start + int(chunk_size * 0.6)
            split_at = text.rfind(" ", window_start, end)
            if split_at > start:
                end = split_at

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= length:
            break

        next_start = end - overlap
        if next_start <= start:
            next_start = start + chunk_size
        start = next_start

    return chunks


def extract_pdf_pages(pdf_path: Path) -> List[Tuple[int, str]]:
    pages: List[Tuple[int, str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = clean_text(page.extract_text() or "")
            if page_text:
                pages.append((page_number, page_text))
    return pages


def make_chunk_id(filename: str, page: int, chunk_idx: int) -> str:
    raw = f"{filename}|p{page}|c{chunk_idx}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_rows_from_pdf(pdf_path: Path) -> List[Dict]:
    filename = pdf_path.name
    rows: List[Dict] = []

    pages = extract_pdf_pages(pdf_path)
    for page_number, page_text in pages:
        chunks = chunk_text(
            text=page_text,
            chunk_size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
        )
        for chunk_idx, chunk in enumerate(chunks):
            rows.append(
                {
                    "id": make_chunk_id(filename, page_number, chunk_idx),
                    "document": chunk,
                    "metadata": {
                        "source": filename,
                        "page": page_number,
                        "chunk_index": chunk_idx,
                    },
                }
            )

    return rows


def upsert_rows(collection, model: SentenceTransformer, rows: List[Dict], batch_size: int) -> None:
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        documents = [r["document"] for r in batch]
        ids = [r["id"] for r in batch]
        metadatas = [r["metadata"] for r in batch]

        embeddings = model.encode(
            documents,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings.tolist(),
        )


def source_already_indexed(collection, source_name: str) -> bool:
    existing = collection.get(where={"source": source_name}, limit=1)
    ids = existing.get("ids", [])
    return bool(ids)


def run_ingest(input_dir: Path, reset: bool, batch_size: int, skip_existing: bool = True) -> None:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir does not exist: {input_dir}")

    pdf_paths = sorted(input_dir.glob("*.pdf"))
    if not pdf_paths:
        print(f"[INFO] No PDFs found in: {input_dir}")
        return

    chroma_path = Path(settings.CHROMA_PATH)
    chroma_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name=settings.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    if reset:
        print(f"[INFO] Reset enabled. Deleting collection: {settings.COLLECTION_NAME}")
        client.delete_collection(name=settings.COLLECTION_NAME)
        collection = client.get_or_create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    print(f"[INFO] Loading embedding model: {settings.EMBED_MODEL}")
    model = SentenceTransformer(settings.EMBED_MODEL)

    total_chunks = 0
    for pdf_path in pdf_paths:
        print(f"[INFO] Processing {pdf_path.name} ...")
        if skip_existing and source_already_indexed(collection, pdf_path.name):
            print(f"[SKIP] {pdf_path.name}: already indexed")
            continue

        rows = build_rows_from_pdf(pdf_path)
        if not rows:
            print(f"[WARN] No text/chunks found in {pdf_path.name}")
            continue

        upsert_rows(collection=collection, model=model, rows=rows, batch_size=batch_size)
        total_chunks += len(rows)
        print(f"[OK] {pdf_path.name}: {len(rows)} chunks indexed")

    print("")
    print("[DONE] Ingest complete")
    print(f"Collection: {settings.COLLECTION_NAME}")
    print(f"Path: {settings.CHROMA_PATH}")
    print(f"PDFs processed: {len(pdf_paths)}")
    print(f"Total chunks: {total_chunks}")


if __name__ == "__main__":
    input_dir = DEFAULT_INPUT_DIR
    batch_size = 64
    reset = False
    skip_existing = True

    run_ingest(
        input_dir=input_dir,
        reset=reset,
        batch_size=batch_size,
        skip_existing=skip_existing,
    )
