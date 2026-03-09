from app.rag.loader import load_pdf
from app.rag.cleaner import clean_text
from app.rag.chunker import split_text
from app.rag.embeddings import create_embedding
from app.rag.vector_store import store_vectors


async def process_tender(file):
    print("Tender processing started")

    text = load_pdf(file.file)

    print("Text extracted length:", len(text))

    clean = clean_text(text)
    chunks = split_text(clean)

    print("Total chunks:", len(chunks))

    if not chunks:
        return {"chunks": 0}

    embeddings = [create_embedding(chunk) for chunk in chunks]

    store_vectors(chunks, embeddings, index_name="tender")

    return {
        "chunks": len(chunks)
    }
