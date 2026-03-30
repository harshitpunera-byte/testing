from typing import Dict, List

from app.rag.vector_store import get_chunk_window, get_document_chunks, search_index, search_index_hybrid


TENDER_INDEX_NAME = "tender"


def search_tender_vectors(query: str, top_k: int = 3) -> List[Dict]:
    return search_index(TENDER_INDEX_NAME, query, top_k)


def search_tender_vectors_hybrid(query: str, top_k: int = 6, document_id: int | None = None) -> List[Dict]:
    return search_index_hybrid(TENDER_INDEX_NAME, query, top_k, document_id=document_id)


def get_tender_document_chunks(
    filename: str | None = None,
    limit: int | None = None,
    document_id: int | None = None,
) -> List[Dict]:
    return get_document_chunks(TENDER_INDEX_NAME, filename=filename, limit=limit, document_id=document_id)


def get_tender_chunk_window(
    *,
    center_chunk_id: int | None,
    window: int = 1,
    filename: str | None = None,
    document_id: int | None = None,
) -> List[Dict]:
    return get_chunk_window(
        TENDER_INDEX_NAME,
        center_chunk_id=center_chunk_id,
        window=window,
        filename=filename,
        document_id=document_id,
    )
