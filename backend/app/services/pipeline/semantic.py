"""
semantic.py — EduCheck Hybrid Pipeline · Stage 4
──────────────────────────────────────────────────
Sentence-level semantic similarity using BERT embeddings.

Key design
──────────
· Singleton model (loaded once at import time, reused across requests).
· Sentence-to-sentence comparison (NOT sentence-to-full-document).
· Batched encoding for both submission sentences and reference sentences.
· Optional FAISS index for scalable ANN search when the reference corpus
  grows large (falls back to brute-force cosine if FAISS is unavailable).
"""

from __future__ import annotations

import numpy as np
from typing import List, Optional, Tuple

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity as sk_cosine

# ---------------------------------------------------------------------------
# Singleton model
# ---------------------------------------------------------------------------

_MODEL: Optional[SentenceTransformer] = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def encode_sentences(
    sentences: List[str],
    batch_size: int = 64,
    normalize: bool = True,
) -> np.ndarray:
    """
    Encode a list of sentences → (N, 384) float32 numpy array.

    Parameters
    ──────────
    sentences  : list of raw sentence strings
    batch_size : encoder batch size (tune to GPU/CPU RAM)
    normalize  : L2-normalize embeddings (required for dot-product = cosine)
    """
    model = get_model()
    embeddings = model.encode(
        sentences,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=normalize,
        show_progress_bar=False,
    )
    return embeddings.astype(np.float32)


# ---------------------------------------------------------------------------
# Sentence × Sentence cosine similarity matrix
# ---------------------------------------------------------------------------

def sentence_cosine_matrix(
    query_embeddings: np.ndarray,
    ref_embeddings: np.ndarray,
) -> np.ndarray:
    """
    Return an (N_query × N_ref) cosine similarity matrix.

    Both inputs are assumed to be L2-normalised, so the matrix is just
    the dot product (fast). Falls back to sklearn for unnormalised input.
    """
    # dot product when normalised ≡ cosine similarity
    return query_embeddings @ ref_embeddings.T


# ---------------------------------------------------------------------------
# FAISS-accelerated nearest-neighbour search (optional)
# ---------------------------------------------------------------------------

try:
    import faiss as _faiss
    _HAS_FAISS = True
except ImportError:
    _HAS_FAISS = False


def faiss_top_k(
    query_embeddings: np.ndarray,
    ref_embeddings: np.ndarray,
    top_k: int = 1,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Use FAISS inner-product index (≡ cosine for normalised vectors) to
    return the top-K reference indices and scores for each query sentence.

    Returns
    ───────
    scores  : (N_query, top_k) float32
    indices : (N_query, top_k) int64  — index into ref_embeddings

    Falls back to brute-force numpy when FAISS is not installed.
    """
    if not _HAS_FAISS:
        # Brute-force fallback
        sim = sentence_cosine_matrix(query_embeddings, ref_embeddings)
        # top-k per row
        indices = np.argsort(-sim, axis=1)[:, :top_k]
        scores  = np.take_along_axis(sim, indices, axis=1)
        return scores, indices

    dim   = ref_embeddings.shape[1]
    index = _faiss.IndexFlatIP(dim)
    index.add(ref_embeddings)

    scores, indices = index.search(query_embeddings, top_k)
    return scores, indices


# ---------------------------------------------------------------------------
# Public API: compare submission sentences vs. reference sentences
# ---------------------------------------------------------------------------

def compute_semantic_matches(
    sub_sentences: List[str],
    ref_sentences: List[str],
    threshold: float = 0.70,
    use_faiss: bool = True,
) -> List[dict]:
    """
    For each submission sentence, find the most similar reference sentence.

    Parameters
    ──────────
    sub_sentences : raw submission sentences
    ref_sentences : raw reference sentences (e.g. paper abstract sentences)
    threshold     : minimum cosine similarity to flag a match
    use_faiss     : whether to attempt FAISS ANN (falls back automatically)

    Returns
    ───────
    List of match dicts, one per *flagged* submission sentence:
    {
      "sub_idx":      int,    # index in sub_sentences
      "ref_idx":      int,    # index in ref_sentences
      "sub_sentence": str,
      "ref_sentence": str,
      "semantic_score": float,
    }
    """
    if not sub_sentences or not ref_sentences:
        return []

    sub_emb = encode_sentences(sub_sentences)
    ref_emb = encode_sentences(ref_sentences)

    if use_faiss or _HAS_FAISS:
        scores, indices = faiss_top_k(sub_emb, ref_emb, top_k=1)
        matches = []
        for i, (score_row, idx_row) in enumerate(zip(scores, indices)):
            best_score = float(score_row[0])
            best_ref   = int(idx_row[0])
            if best_score >= threshold:
                matches.append({
                    "sub_idx":        i,
                    "ref_idx":        best_ref,
                    "sub_sentence":   sub_sentences[i],
                    "ref_sentence":   ref_sentences[best_ref],
                    "semantic_score": round(best_score, 4),
                })
    else:
        sim_matrix = sentence_cosine_matrix(sub_emb, ref_emb)
        matches = []
        for i in range(len(sub_sentences)):
            best_ref   = int(np.argmax(sim_matrix[i]))
            best_score = float(sim_matrix[i][best_ref])
            if best_score >= threshold:
                matches.append({
                    "sub_idx":        i,
                    "ref_idx":        best_ref,
                    "sub_sentence":   sub_sentences[i],
                    "ref_sentence":   ref_sentences[best_ref],
                    "semantic_score": round(best_score, 4),
                })

    return matches