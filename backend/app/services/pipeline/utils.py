"""
utils.py — EduCheck Academic Check
────────────────────────────────────
Stage 1: Preprocessing helpers shared across all pipeline stages.
"""

import re
import string
from typing import List
from collections import Counter

# ── Optional NLTK (graceful fallback) ────────────────────────────────────────
try:
    import nltk
    from nltk.tokenize import sent_tokenize, word_tokenize
    from nltk.corpus import stopwords

    for _pkg in ("punkt", "punkt_tab", "stopwords"):
        try:
            nltk.data.find(
                f"tokenizers/{_pkg}" if "punkt" in _pkg else f"corpora/{_pkg}"
            )
        except LookupError:
            nltk.download(_pkg, quiet=True)

    _STOP_WORDS: set = set(stopwords.words("english"))
    _USE_NLTK = True
except Exception:
    _USE_NLTK = False
    _STOP_WORDS = {
        "a","an","the","and","or","but","in","on","at","to","for","of","with",
        "by","from","is","was","are","were","be","been","has","have","had","do",
        "does","did","will","would","could","should","may","might","shall","can",
        "this","that","these","those","it","its","i","we","you","he","she","they",
        "their","our","your","his","her","as","if","so","not","no","nor","just",
        "also","into","than","then","when","which","who","what","where","how",
    }


def split_sentences(text: str, min_len: int = 20) -> List[str]:
    """Split raw text into sentences, discard very short ones."""
    if not text or not text.strip():
        return []
    if _USE_NLTK:
        raw = sent_tokenize(text)
    else:
        raw = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw if len(s.strip()) >= min_len]


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, remove stopwords."""
    if not text:
        return ""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split()
    tokens = [t for t in tokens if t.isalpha() and t not in _STOP_WORDS]
    return " ".join(tokens)


def extract_keywords(text: str, top_k: int = 8) -> List[str]:
    """
    Extract top-k meaningful keywords from text using TF-style frequency.
    Returns individual keywords AND 2-word bigrams for richer API queries.
    """
    norm = normalize_text(text)
    tokens = norm.split()

    if not tokens:
        # Fallback: just take first 100 chars
        return [text[:100]]

    # Unigram frequencies
    freq = Counter(tokens)

    # Top single keywords
    top_words = [w for w, _ in freq.most_common(top_k) if len(w) > 3]

    # Build bigrams from top words for more precise queries
    bigrams = []
    for i in range(len(tokens) - 1):
        if tokens[i] in set(top_words) and tokens[i+1] in set(top_words):
            bigrams.append(f"{tokens[i]} {tokens[i+1]}")

    # Deduplicate bigrams
    seen = set()
    unique_bigrams = []
    for b in bigrams:
        if b not in seen:
            seen.add(b)
            unique_bigrams.append(b)

    # Combine: prefer bigrams, fill with single words
    queries = unique_bigrams[:4] + [w for w in top_words if w not in " ".join(unique_bigrams)]
    return queries[:top_k] if queries else top_words[:top_k]


def clean_abstract(text: str) -> str:
    """Remove LaTeX, HTML tags, excessive whitespace from paper abstracts."""
    if not text:
        return ""
    # Remove LaTeX commands
    text = re.sub(r'\$[^$]*\$', '', text)
    text = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def truncate(text: str, max_chars: int = 2000) -> str:
    """Truncate long texts to avoid embedding bottlenecks."""
    if not text:
        return ""
    return text[:max_chars] if len(text) > max_chars else text