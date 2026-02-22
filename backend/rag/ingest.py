import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import chromadb
import pdfplumber
from sentence_transformers import SentenceTransformer

from backend.config import appSettings


settings = appSettings()

DEFAULT_INPUT_DIR = Path("data/rag/raw_pdfs")
DEFAULT_BATCH_SIZE = 64
_EMBEDDING_MODEL: SentenceTransformer | None = None


def sanitize_pdf_filename(filename: str) -> str:
    cleaned = Path((filename or "").strip()).name
    if not cleaned:
        raise ValueError("Nombre de archivo invalido.")
    if not cleaned.lower().endswith(".pdf"):
        raise ValueError("Solo se permiten archivos PDF.")
    return cleaned


def get_or_create_collection():
    chroma_path = Path(settings.CHROMA_PATH)
    chroma_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_path))
    return client.get_or_create_collection(
        name=settings.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def get_embedding_model() -> SentenceTransformer:
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        print(f"[INFO] Loading embedding model: {settings.EMBED_MODEL}")
        _EMBEDDING_MODEL = SentenceTransformer(settings.EMBED_MODEL)
    return _EMBEDDING_MODEL


def _flatten_ids(raw_ids: Any) -> List[str]:
    if not raw_ids:
        return []
    if isinstance(raw_ids, list):
        if raw_ids and isinstance(raw_ids[0], list):
            return [str(item) for group in raw_ids for item in group]
        return [str(item) for item in raw_ids]
    return []


def clean_text(text: str) -> str:
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Divide el texto recursivamente usando una jerarquía de separadores para 
    mantener el contexto semántico (párrafos -> líneas -> frases -> palabras).
    """
    if not text:
        return []

    if overlap >= chunk_size:
        raise ValueError("CHUNK_OVERLAP debe ser menor que CHUNK_SIZE.")

    # Jerarquía de separadores de mayor a menor significado semántico
    separators = ["\n\n", "\n", ". ", " "]

    def _split(text_to_split: str, sep_index: int) -> List[str]:
        # Condición de parada: el texto ya cabe en un chunk
        if len(text_to_split) <= chunk_size:
            return [text_to_split]

        # Si nos quedamos sin separadores, cortamos por caracteres brutos
        if sep_index >= len(separators):
            return [text_to_split[i:i+chunk_size] for i in range(0, len(text_to_split), chunk_size - overlap)]

        separator = separators[sep_index]
        
        # Dividir el texto
        if separator == ". ":
            # Truco para no perder el punto al final de las frases
            splits = [s + ". " for s in text_to_split.split(". ") if s]
        else:
            splits = text_to_split.split(separator)

        chunks = []
        current_chunk_pieces = []
        current_length = 0

        for split in splits:
            split_len = len(split) if separator == ". " else len(split) + len(separator)

            if len(split) > chunk_size:
                if current_chunk_pieces:
                    chunks.append(separator.join(current_chunk_pieces).strip())
                    current_chunk_pieces = []
                    current_length = 0
                
                sub_chunks = _split(split, sep_index + 1)
                chunks.extend(sub_chunks)
                continue

            if current_length + len(split) > chunk_size and current_chunk_pieces:
                chunks.append(separator.join(current_chunk_pieces).strip())
                
                overlap_length = 0
                overlap_pieces = []
                for piece in reversed(current_chunk_pieces):
                    if overlap_length + len(piece) > overlap:
                        break
                    overlap_pieces.insert(0, piece)
                    overlap_length += len(piece) + len(separator)
                
                current_chunk_pieces = overlap_pieces
                current_length = sum(len(p) + len(separator) for p in current_chunk_pieces)

            current_chunk_pieces.append(split)
            current_length += split_len
        if current_chunk_pieces:
            chunks.append(separator.join(current_chunk_pieces).strip())

        return chunks

    return [c.strip() for c in _split(text, 0) if c.strip()]


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


def delete_source_chunks(collection, source_name: str) -> int:
    existing = collection.get(where={"source": source_name}, include=["metadatas"])
    ids = _flatten_ids(existing.get("ids", []))
    if not ids:
        return 0
    collection.delete(ids=ids)
    return len(ids)


def ingest_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    input_dir: Path = DEFAULT_INPUT_DIR,
) -> Dict[str, Any]:
    if not pdf_bytes:
        raise ValueError("El PDF esta vacio.")

    source_name = sanitize_pdf_filename(filename)
    input_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = input_dir / source_name
    pdf_path.write_bytes(pdf_bytes)

    collection = get_or_create_collection()
    replaced_chunks = delete_source_chunks(collection, source_name)

    rows = build_rows_from_pdf(pdf_path)
    if not rows:
        pdf_path.unlink(missing_ok=True)
        raise ValueError(f"No se encontro texto util en '{source_name}'.")

    model = get_embedding_model()
    upsert_rows(collection=collection, model=model, rows=rows, batch_size=batch_size)

    return {
        "source": source_name,
        "chunks_indexed": len(rows),
        "chunks_replaced": replaced_chunks,
    }


def list_indexed_sources(input_dir: Path = DEFAULT_INPUT_DIR) -> List[Dict[str, Any]]:
    input_dir.mkdir(parents=True, exist_ok=True)
    collection = get_or_create_collection()

    data = collection.get(include=["metadatas"])
    metadatas = data.get("metadatas", []) or []

    chunk_count_by_source: Dict[str, int] = {}
    for metadata in metadatas:
        if not isinstance(metadata, dict):
            continue
        source = metadata.get("source")
        if not source:
            continue
        chunk_count_by_source[source] = chunk_count_by_source.get(source, 0) + 1

    documents: List[Dict[str, Any]] = []
    for source, chunk_count in chunk_count_by_source.items():
        pdf_path = input_dir / source
        uploaded_at = None
        file_exists = pdf_path.exists()
        if file_exists:
            uploaded_at = datetime.fromtimestamp(
                pdf_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()

        documents.append(
            {
                "source": source,
                "chunk_count": chunk_count,
                "uploaded_at": uploaded_at,
                "file_exists": file_exists,
            }
        )

    documents.sort(key=lambda item: item["source"].lower())
    return documents


def delete_indexed_source(
    source_name: str,
    input_dir: Path = DEFAULT_INPUT_DIR,
    delete_file: bool = True,
) -> Dict[str, Any]:
    source_name = sanitize_pdf_filename(source_name)
    collection = get_or_create_collection()
    deleted_chunks = delete_source_chunks(collection, source_name)

    deleted_file = False
    pdf_path = input_dir / source_name
    if delete_file and pdf_path.exists():
        pdf_path.unlink()
        deleted_file = True

    return {
        "source": source_name,
        "deleted_chunks": deleted_chunks,
        "deleted_file": deleted_file,
        "deleted": bool(deleted_chunks or deleted_file),
    }

