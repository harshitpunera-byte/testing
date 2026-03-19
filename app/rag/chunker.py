from app.rag.semantic_structurer import build_semantic_blocks


def split_text(text, chunk_size=800, overlap=150):
    words = text.split()
    chunks = []

    if not words:
        return chunks

    start = 0
    step = max(1, chunk_size - overlap)

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end]).strip()

        if chunk:
            chunks.append(chunk)

        start += step

    return chunks


def chunk_blocks(
    blocks: list[dict],
    *,
    chunk_size: int = 800,
    overlap: int = 150,
    filename: str = "unknown.pdf",
    document_id: int | None = None,
    document_type: str | None = None,
) -> list[dict]:
    chunk_records = []
    next_chunk_id = 0

    for block in blocks:
        block_text = block.get("text", "")
        block_chunks = split_text(block_text, chunk_size=chunk_size, overlap=overlap)

        for chunk_text in block_chunks:
            chunk_records.append(
                {
                    "filename": filename,
                    "text": chunk_text,
                    "chunk_id": next_chunk_id,
                    "document_id": document_id,
                    "document_type": document_type,
                    "section": block.get("section", "general"),
                    "page_start": block.get("page_start"),
                    "page_end": block.get("page_end"),
                    "embedding_backend": "pgvector",
                    "chunk_type": "semantic",
                    "token_count": len(chunk_text.split()),
                }
            )
            next_chunk_id += 1

    return chunk_records


def chunk_document_pages(
    pages: list,
    *,
    document_type: str,
    chunk_size: int = 800,
    overlap: int = 150,
    filename: str = "unknown.pdf",
    document_id: int | None = None,
) -> list[dict]:
    semantic_blocks = build_semantic_blocks(pages, document_type=document_type)
    return chunk_blocks(
        semantic_blocks,
        chunk_size=chunk_size,
        overlap=overlap,
        filename=filename,
        document_id=document_id,
        document_type=document_type,
    )
