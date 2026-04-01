"""
retrieval.py — EduCheck Hybrid Pipeline · Stage 2
──────────────────────────────────────────────────
BM25-based candidate retrieval.

Indexes all source documents (academic paper abstracts) and retrieves
the top-K most relevant ones for a given query BEFORE any expensive
embedding or fingerprinting work is done.

Key design decisions
────────────────────
· Uses rank-bm25 (BM25Okapi).  Falls back to a simple TF-IDF-style
  frequency match if the library is missing, so the pipeline never
  hard-crashes at import time.
· Accepts pre-normalized token lists (from preprocessing.py) so no
  double-normalization happens.
· Stateless per-call — no global index state.  The caller builds an
  ephemeral BM25Retriever per request from the set of candidate papers.
"""

from __future__ import annotations

import re
import string
from typing import List, Tuple, Dict, Any

# ---------------------------------------------------------------------------
# Optional rank-bm25 — hard requirement but graceful import message
# ---------------------------------------------------------------------------
try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False
    print(
        "[retrieval] WARNING: rank-bm25 not installed.  "
        "Falling back to naive token-overlap scoring.  "
        "Run: pip install rank-bm25"
    )


# ---------------------------------------------------------------------------
# Tokeniser helper (shared, lightweight)
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","was","are","were","be","been","has","have","had","do",
    "does","did","will","would","could","should","may","might","this","that",
    "it","its","we","you","he","she","they","their","as","if","so","not",
}

def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, split, remove stopwords."""
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return [t for t in text.split() if t.isalpha() and t not in _STOPWORDS]


# ---------------------------------------------------------------------------
# BM25Retriever
# ---------------------------------------------------------------------------

class BM25Retriever:
    """
    Build a BM25 index from a list of documents, then retrieve top-K
    most relevant documents for any query string.

    Usage
    ─────
    >>> docs = [{"id": "p1", "text": "deep learning transformers …"}, …]
    >>> retriever = BM25Retriever(docs, text_key="text")
    >>> top = retriever.retrieve(query_text, top_k=15)
    # Returns: List[dict] — the original doc dicts for the top-K matches
    """

    def __init__(
        self,
        documents: List[Dict[str, Any]],
        text_key: str = "text",
    ) -> None:
        """
        Parameters
        ──────────
        documents : list of dicts, each must contain the key `text_key`
        text_key  : which field in each dict to index
        """
        self._docs      = documents
        self._text_key  = text_key
        self._tokenized = [_tokenize(d.get(text_key, "")) for d in documents]

        if _HAS_BM25 and self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)
        else:
            self._bm25 = None

    # ------------------------------------------------------------------
    def retrieve(self, query: str, top_k: int = 15) -> List[Dict[str, Any]]:
        """
        Return up to `top_k` documents most relevant to `query`.

        Returns an empty list if the index is empty.
        """
        if not self._docs:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return self._docs[:top_k]

        if self._bm25 is not None:
            scores  = self._bm25.get_scores(query_tokens)
            ranked  = sorted(
                range(len(self._docs)),
                key=lambda i: scores[i],
                reverse=True,
            )
        else:
            # Fallback: simple Jaccard-overlap score
            query_set = set(query_tokens)
            ranked = sorted(
                range(len(self._docs)),
                key=lambda i: len(query_set & set(self._tokenized[i])) / max(
                    len(query_set | set(self._tokenized[i])), 1
                ),
                reverse=True,
            )

        top_indices = ranked[:top_k]
        return [self._docs[i] for i in top_indices]


# ---------------------------------------------------------------------------
# Convenience: retrieve from a raw list of texts
# ---------------------------------------------------------------------------

def retrieve_top_k(
    query: str,
    candidate_texts: List[str],
    top_k: int = 15,
) -> List[Tuple[int, str]]:
    """
    Thin convenience wrapper.

    Returns a list of (original_index, text) tuples for the top-K
    candidates, without requiring the caller to build a dict list.
    """
    docs = [{"text": t, "idx": i} for i, t in enumerate(candidate_texts)]
    retriever = BM25Retriever(docs, text_key="text")
    results   = retriever.retrieve(query, top_k=top_k)
    return [(d["idx"], d["text"]) for d in results]