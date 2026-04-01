"""
preprocessing.py — EduCheck Hybrid Pipeline · Stage 1
───────────────────────────────────────────────────────
Normalize text and split into sentences.

Used by:
  · retrieval.py    (BM25 indexing)
  · fingerprinting.py (shingling)
  · semantic.py     (embedding)
"""

import re
import string
from typing import List

# ---------------------------------------------------------------------------
# Optional NLTK — graceful fallback if not installed
# ---------------------------------------------------------------------------
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
        "their","our","your","his","her","as","if","so","not","no","nor",
    }


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def split_sentences(text: str, min_len: int = 15) -> List[str]:
    """
    Split *raw* text into individual sentences.
    Sentences shorter than `min_len` characters are discarded.
    """
    if not text or not text.strip():
        return []

    if _USE_NLTK:
        raw = sent_tokenize(text)
    else:
        raw = re.split(r'(?<=[.!?])\s+', text.strip())

    return [s.strip() for s in raw if len(s.strip()) >= min_len]


def normalize_text(text: str) -> str:
    """
    Full normalization pipeline:
      lowercase → strip punctuation → remove stopwords → collapse whitespace.

    Returns a clean token string suitable for BM25 / Jaccard / shingling.
    """
    if not text:
        return ""

    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()

    if _USE_NLTK:
        tokens = word_tokenize(text)
    else:
        tokens = text.split()

    tokens = [t for t in tokens if t.isalpha() and t not in _STOP_WORDS]
    return " ".join(tokens)


def normalize_sentence(sentence: str) -> str:
    """Normalize a single sentence (thin wrapper for readability)."""
    return normalize_text(sentence)


# ---------------------------------------------------------------------------
# Document preprocessor — main entry point for the pipeline
# ---------------------------------------------------------------------------

class DocumentPreprocessor:
    """
    Converts raw text into a structured document dict consumed by every
    downstream pipeline stage.

    Output schema
    ─────────────
    {
      "raw_text":       str,         # original text, stripped
      "sentences":      List[str],   # raw sentences
      "norm_sentences": List[str],   # normalized sentences (BM25 / shingles)
      "norm_full":      str,         # single joined normalized string
    }
    """

    def process(self, text: str) -> dict:
        if not text or not text.strip():
            return {
                "raw_text": "",
                "sentences": [],
                "norm_sentences": [],
                "norm_full": "",
            }

        sentences      = split_sentences(text)
        norm_sentences = [normalize_sentence(s) for s in sentences]

        return {
            "raw_text":       text.strip(),
            "sentences":      sentences,
            "norm_sentences": norm_sentences,
            "norm_full":      " ".join(norm_sentences),
        }