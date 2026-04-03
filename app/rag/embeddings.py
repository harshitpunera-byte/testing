import hashlib
import os
from typing import Iterable, List

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en"
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

_model = None
_model_failed = False


def _hash_embedding(text: str) -> np.ndarray:
    vector = np.zeros(EMBEDDING_DIM, dtype="float32")

    for token in str(text).lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm

    return vector


def _get_model():
    global _model, _model_failed

    if _model is not None:
        return _model

    if _model_failed:
        return None

    try:
        _model = SentenceTransformer(MODEL_NAME)
        return _model
    except Exception as exc:
        _model_failed = True
        import logging
        logging.getLogger(__name__).error(f"CRITICAL: Embedding model {MODEL_NAME} failed to load! Falling back to non-semantic SHA256 hashes. RAG retrieval will severely degrade. Error: {exc}")
        print(f"CRITICAL WARNING: Embedding model {MODEL_NAME} unavailable. Generating non-semantic SHA256 hash fallback: {exc}")
        return None


def create_embedding(text: str) -> np.ndarray:
    model = _get_model()
    if model is None:
        return _hash_embedding(text)

    vector = model.encode(text)
    vector = np.asarray(vector, dtype="float32")
    if vector.shape[0] != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch for {MODEL_NAME}: expected {EMBEDDING_DIM}, got {vector.shape[0]}"
        )
    return vector


def create_embeddings(texts: Iterable[str]) -> np.ndarray:
    text_list: List[str] = [str(text) for text in texts]

    if not text_list:
        return np.empty((0, EMBEDDING_DIM), dtype="float32")

    model = _get_model()
    if model is None:
        vectors = [_hash_embedding(text) for text in text_list]
        return np.asarray(vectors, dtype="float32")

    vectors = model.encode(text_list)
    vectors = np.asarray(vectors, dtype="float32")
    if vectors.shape[1] != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch for {MODEL_NAME}: expected {EMBEDDING_DIM}, got {vectors.shape[1]}"
        )
    return vectors
