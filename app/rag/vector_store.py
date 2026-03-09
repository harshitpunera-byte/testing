import faiss
import os
import pickle
import numpy as np

VECTOR_PATH = "vector_store"

def store_vectors(chunks, embeddings, index_name):

    os.makedirs(VECTOR_PATH, exist_ok=True)

    index_path = f"{VECTOR_PATH}/{index_name}_index.faiss"
    meta_path = f"{VECTOR_PATH}/{index_name}_metadata.pkl"

    dim = len(embeddings[0])

    if os.path.exists(index_path):
        index = faiss.read_index(index_path)
    else:
        index = faiss.IndexFlatL2(dim)

    if os.path.exists(meta_path):
        with open(meta_path, "rb") as f:
            metadata = pickle.load(f)
    else:
        metadata = []
        with open(meta_path, "wb") as f:
            pickle.dump(metadata, f)

    index.add(np.array(embeddings, dtype="float32"))

    metadata.extend(chunks)

    faiss.write_index(index, index_path)

    with open(meta_path, "wb") as f:
        pickle.dump(metadata, f)

    print("Vector stored in FAISS:", index_name)
