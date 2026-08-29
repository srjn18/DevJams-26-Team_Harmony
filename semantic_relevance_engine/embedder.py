"""
Embedding module for Semantic Relevance Engine.

Implements a 3-tier embedding architecture:
1. Local `sentence_transformers` (e.g. all-MiniLM-L6-v2) if installed.
2. OpenAI embeddings endpoint if `OPENAI_API_KEY` is set in environment.
3. Zero-dependency Pure Python / NumPy Subword N-Gram Hashing Vectorizer with L2 normalization (works offline, zero installation required).
"""

import os
import re
import json
import math
import hashlib
from typing import List, Optional
import numpy as np

# Embedding dimension for hash-vectorizer fallback
HASH_EMBEDDING_DIM = 256

# Singleton instances
_sentence_transformer_model = None
_sentence_transformer_checked = False


def _get_sentence_transformer():
    global _sentence_transformer_model, _sentence_transformer_checked
    if not _sentence_transformer_checked:
        _sentence_transformer_checked = True
        try:
            from sentence_transformers import SentenceTransformer
            _sentence_transformer_model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            _sentence_transformer_model = None
    return _sentence_transformer_model


def _call_openai_embeddings(texts: List[str]) -> Optional[List[List[float]]]:
    """Call OpenAI embeddings API using standard library urllib."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    import urllib.request
    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "input": texts,
        "model": "text-embedding-3-small"
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            data_sorted = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in data_sorted]
    except Exception:
        return None


def _hash_vectorize(text: str, dim: int = HASH_EMBEDDING_DIM) -> List[float]:
    """
    High-performance zero-dependency subword n-gram hashing vectorizer.
    Produces an L2-normalized dense vector of size `dim` capturing word and subword frequencies.
    """
    clean_text = text.lower().strip()
    if not clean_text:
        return [0.0] * dim

    words = re.findall(r'\b\w+\b', clean_text)
    vec = np.zeros(dim, dtype=np.float32)

    # Word-level features
    for word in words:
        # MD5 hashing to bucket
        h = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16) % dim
        vec[h] += 1.5

        # Subword char n-grams (3, 4)
        for n in (3, 4):
            if len(word) >= n:
                for i in range(len(word) - n + 1):
                    sub = word[i:i + n]
                    sub_h = int(hashlib.md5(sub.encode('utf-8')).hexdigest(), 16) % dim
                    vec[sub_h] += 0.5

    # L2 normalize
    norm = np.linalg.norm(vec)
    if norm > 1e-9:
        vec = vec / norm
    return vec.tolist()


class Embedder:
    """Pluggable multi-tier embedder."""

    @classmethod
    def embed_texts(cls, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        # Tier 1: Local sentence-transformers
        st_model = _get_sentence_transformer()
        if st_model is not None:
            try:
                embeddings = st_model.encode(texts, normalize_embeddings=True)
                return [emb.tolist() for emb in embeddings]
            except Exception:
                pass

        # Tier 2: OpenAI API if key configured
        openai_embs = _call_openai_embeddings(texts)
        if openai_embs is not None:
            return openai_embs

        # Tier 3: Pure NumPy Subword Hashing Vectorizer (Zero-Dependency)
        return [_hash_vectorize(t) for t in texts]

    @classmethod
    def embed_query(cls, query: str) -> List[float]:
        return cls.embed_texts([query])[0]

    @classmethod
    def embed_chunks(cls, texts: List[str]) -> List[List[float]]:
        return cls.embed_texts(texts)
