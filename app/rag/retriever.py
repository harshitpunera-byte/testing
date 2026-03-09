import faiss
import pickle
import numpy as np
import os

from app.rag.embeddings import create_embedding

VECTOR_PATH = "vector_store"


def search_resume_vectors(query_text, k=3):
    index_path = f"{VECTOR_PATH}/resume_index.faiss"
    meta_path = f"{VECTOR_PATH}/resume_metadata.pkl"

    if not os.path.exists(index_path):
        return []

    if not os.path.exists(meta_path):
        return []

    index = faiss.read_index(index_path)

    with open(meta_path, "rb") as f:
        metadata = pickle.load(f)

    # Convert query text → embedding
    query_embedding = create_embedding(query_text)

    if index.ntotal == 0 or not metadata:
        return []

    query_vector = np.array([query_embedding], dtype="float32")

    distances, indices = index.search(query_vector, min(k, index.ntotal))

    results = []

    for idx in indices[0]:
        if idx < len(metadata):
            results.append(metadata[idx])

    return results
