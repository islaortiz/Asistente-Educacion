from typing import Any, Dict, List

from backend.rag.ingest import get_embedding_model, get_or_create_collection


def retrieve_chunks(
    query: str,
    source_name: str | None = None,
    n_results: int = 1,
) -> List[Dict[str, Any]]:
    """Busca los chunks mas similares a la query. Filtra por source si se indica."""
    collection = get_or_create_collection()
    model = get_embedding_model()

    query_embedding = model.encode(
        [query], normalize_embeddings=True
    ).tolist()

    where_filter = {"source": source_name} if source_name else None

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists):
        chunks.append(
            {
                "text": doc,
                "source": meta.get("source", ""),
                "page": meta.get("page", 0),
                "distance": dist,
            }
        )

    return chunks
