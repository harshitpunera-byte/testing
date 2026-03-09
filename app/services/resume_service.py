from app.rag.loader import load_pdf
from app.rag.cleaner import clean_text
from app.rag.chunker import split_text
from app.rag.embeddings import create_embedding
from app.rag.vector_store import store_vectors
from app.models.vector_metadata import add_metadata

import uuid


async def process_resume(file):

    resume_id = str(uuid.uuid4())

    print("Resume processing started")

    text = load_pdf(file.file)

    print("Text extracted length:", len(text))

    clean = clean_text(text)

    chunks = split_text(clean)

    print("Total chunks:", len(chunks))

    if not chunks:
        return {"resume_id": resume_id}

    embeddings = []

    for chunk in chunks:
        vector = create_embedding(chunk)
        embeddings.append(vector)

        print("Vector created")

        add_metadata({
            "resume_id": resume_id,
            "text": chunk,
            "file_name": file.filename
        })

    store_vectors(chunks, embeddings, index_name="resume")

    print("Resume stored successfully")

    return {"resume_id": resume_id}
