"""
fingerprinting.py — EduCheck Hybrid Pipeline · Stage 3
────────────────────────────────────────────────────────
Exact-match detection via shingling + Jaccard similarity.

Algorithm
─────────
1. Build k-shingles (contiguous k-word sequences) from text.
2. Hash each shingle with MD5 → integer fingerprint.
3. Compute Jaccard similarity between two fingerprint sets:
       J(A, B) = |A ∩ B| / |A ∪ B|

This catches copy-paste plagiarism that paraphrasing-aware semantic
models may miss, because it is purely lexical.

Typical threshold: 0.15–0.40 (text reuse is almost never a full-overlap
scenario; even 20 % shingle overlap is suspicious).
"""

from __future__ import annotations

import hashlib
import re
import string
from typing import FrozenSet, Set


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean_tokens(text: str) -> list[str]:
    """Lowercase + remove punctuation → list of alpha tokens."""
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return [t for t in text.split() if t.isalpha()]


def _md5_hash(token: str) -> int:
    """Stable 64-bit integer hash of a string via MD5."""
    return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) & 0xFFFF_FFFF_FFFF_FFFF


# ---------------------------------------------------------------------------
# Core shingling
# ---------------------------------------------------------------------------

def build_shingles(text: str, k: int = 5) -> FrozenSet[int]:
    """
    Return the set of MD5-hashed k-word shingles for `text`.

    Parameters
    ──────────
    text : raw or pre-cleaned text
    k    : shingle width in words (default 5 — good balance of
           precision vs. recall for sentence-length text)

    Returns an empty frozenset for text with fewer than k tokens.
    """
    tokens = _clean_tokens(text)
    if len(tokens) < k:
        return frozenset()

    return frozenset(
        _md5_hash(" ".join(tokens[i : i + k]))
        for i in range(len(tokens) - k + 1)
    )


# ---------------------------------------------------------------------------
# Jaccard similarity
# ---------------------------------------------------------------------------

def jaccard_similarity(set_a: FrozenSet[int], set_b: FrozenSet[int]) -> float:
    """
    Jaccard coefficient between two shingle sets.

    Returns 0.0 when both sets are empty (avoids divide-by-zero).
    Returns 1.0 when sets are identical.
    """
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union        = len(set_a | set_b)
    return intersection / union if union else 0.0


# ---------------------------------------------------------------------------
# Public API: compare two texts
# ---------------------------------------------------------------------------

def fingerprint_similarity(text_a: str, text_b: str, k: int = 5) -> float:
    """
    Compute the Jaccard shingle-similarity between two texts.

    Returns a float in [0.0, 1.0].
    """
    shingles_a = build_shingles(text_a, k=k)
    shingles_b = build_shingles(text_b, k=k)
    return jaccard_similarity(shingles_a, shingles_b)


# ---------------------------------------------------------------------------
# Batch helper: one query vs. many candidates
# ---------------------------------------------------------------------------

def batch_fingerprint_scores(
    query: str,
    candidates: list[str],
    k: int = 5,
) -> list[float]:
    """
    Compute fingerprint similarity of `query` against each candidate.

    Returns a list of floats aligned with `candidates`.
    Pre-builds the query shingles once to avoid redundant work.
    """
    query_shingles = build_shingles(query, k=k)
    if not query_shingles:
        return [0.0] * len(candidates)

    return [
        jaccard_similarity(query_shingles, build_shingles(c, k=k))
        for c in candidates
    ]