"""
academic_plagiarism_service.py
─────────────────────────────
Turnitin-style academic plagiarism checker.

Pipeline:
  1. Extract N-grams / key sentences from the submission
  2. Async-query Semantic Scholar + ArXiv simultaneously
  3. Encode submission sentences + paper abstracts with all-MiniLM-L6-v2
  4. Compute cosine similarity matrix
  5. Return structured JSON with match positions and source metadata
"""

import asyncio
import re
import time
import hashlib
from typing import Optional
from dataclasses import dataclass, field, asdict

import aiohttp
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ── Model (singleton — loaded once) ──────────────────────────────────────────
_model: Optional[SentenceTransformer] = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class PaperSource:
    title:    str
    authors:  list[str]
    url:      str
    abstract: str
    source:   str          # "semantic_scholar" | "arxiv"
    year:     Optional[int] = None


@dataclass
class MatchedSegment:
    text:           str
    start_char:     int
    end_char:       int
    similarity:     float          # 0.0 – 1.0
    similarity_pct: float          # 0 – 100
    source:         PaperSource


@dataclass
class AcademicCheckResult:
    overall_similarity_pct: float
    matched_segments:       list[MatchedSegment]
    sources_checked:        int
    sentences_checked:      int
    elapsed_seconds:        float
    flagged:                bool   # True if overall >= threshold


# ── Text utilities ────────────────────────────────────────────────────────────

def split_sentences(text: str, min_len: int = 20) -> list[str]:
    """Split text into sentences, filter noise."""
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw if len(s.strip()) >= min_len]


def extract_query_phrases(text: str, n: int = 3, top_k: int = 5) -> list[str]:
    """
    Extract the most content-rich N-gram phrases for API querying.
    Removes stopwords, picks longest unique n-grams.
    """
    STOPWORDS = {
        "the","a","an","is","are","was","were","be","been","being",
        "have","has","had","do","does","did","will","would","could","should",
        "may","might","shall","can","need","dare","ought","used",
        "in","on","at","by","for","with","about","against","between","into",
        "through","during","before","after","above","below","to","from",
        "up","down","of","off","over","under","again","further","then",
        "once","that","this","these","those","it","its","they","them",
        "their","we","our","you","your","i","my","he","she","his","her",
        "and","or","but","if","while","although","because","since","as",
    }
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    content_words = [w for w in words if w not in STOPWORDS]

    phrases = []
    for i in range(len(content_words) - n + 1):
        phrase = " ".join(content_words[i:i+n])
        phrases.append(phrase)

    # Deduplicate and take top_k unique phrases spread across the text
    seen = set()
    unique = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    # Pick evenly distributed phrases for broad coverage
    if len(unique) <= top_k:
        return unique
    step = len(unique) // top_k
    return [unique[i * step] for i in range(top_k)]


def find_char_positions(full_text: str, sentence: str) -> tuple[int, int]:
    """Find start/end character positions of a sentence in the full text."""
    idx = full_text.find(sentence)
    if idx == -1:
        # Fuzzy fallback — find closest substring
        for i in range(len(full_text) - len(sentence) + 1):
            if full_text[i:i+len(sentence[:20])] == sentence[:20]:
                return i, i + len(sentence)
    return idx, idx + len(sentence)


# ── Async API fetchers ────────────────────────────────────────────────────────

async def fetch_semantic_scholar(
    session: aiohttp.ClientSession,
    query: str,
    limit: int = 5,
) -> list[PaperSource]:
    """Query Semantic Scholar Graph API — free, no key required."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query":  query,
        "limit":  limit,
        "fields": "title,authors,year,abstract,url,externalIds",
    }
    papers = []
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return papers
            data = await resp.json()
            for p in data.get("data", []):
                abstract = p.get("abstract") or ""
                if len(abstract) < 30:
                    continue  # skip papers with no abstract
                doi = (p.get("externalIds") or {}).get("DOI", "")
                paper_url = p.get("url") or (f"https://doi.org/{doi}" if doi else "")
                papers.append(PaperSource(
                    title    = p.get("title", "Untitled"),
                    authors  = [a["name"] for a in (p.get("authors") or [])[:3]],
                    url      = paper_url,
                    abstract = abstract,
                    source   = "semantic_scholar",
                    year     = p.get("year"),
                ))
    except Exception:
        pass
    return papers


async def fetch_arxiv(
    session: aiohttp.ClientSession,
    query: str,
    limit: int = 5,
) -> list[PaperSource]:
    """Query ArXiv API — completely free, no key needed."""
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "max_results":  limit,
        "sortBy":       "relevance",
    }
    papers = []
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return papers
            text = await resp.text()
            # Parse Atom XML
            entries = re.findall(r'<entry>(.*?)</entry>', text, re.DOTALL)
            for entry in entries:
                title    = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                abstract = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
                link     = re.search(r'<id>(.*?)</id>', entry)
                authors  = re.findall(r'<name>(.*?)</name>', entry)
                year_m   = re.search(r'<published>(\d{4})', entry)

                title_t    = title.group(1).strip()    if title    else "Untitled"
                abstract_t = abstract.group(1).strip() if abstract else ""
                link_t     = link.group(1).strip()     if link     else ""
                year_t     = int(year_m.group(1))      if year_m   else None

                if len(abstract_t) < 30:
                    continue
                papers.append(PaperSource(
                    title    = title_t,
                    authors  = authors[:3],
                    url      = link_t,
                    abstract = abstract_t,
                    source   = "arxiv",
                    year     = year_t,
                ))
    except Exception:
        pass
    return papers


async def fetch_all_papers(queries: list[str]) -> list[PaperSource]:
    """
    Fire all API requests concurrently.
    Each query hits both Semantic Scholar and ArXiv simultaneously.
    """
    async with aiohttp.ClientSession() as session:
        tasks = []
        for q in queries:
            tasks.append(fetch_semantic_scholar(session, q, limit=4))
            tasks.append(fetch_arxiv(session, q, limit=4))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten + deduplicate by title
    seen_titles: set[str] = set()
    papers: list[PaperSource] = []
    for batch in results:
        if isinstance(batch, Exception):
            continue
        for paper in batch:
            key = hashlib.md5(paper.title.lower().encode()).hexdigest()
            if key not in seen_titles:
                seen_titles.add(key)
                papers.append(paper)
    return papers


# ── Core similarity engine ────────────────────────────────────────────────────

def compute_matches(
    submission_text:  str,
    papers:           list[PaperSource],
    threshold:        float = 0.75,
) -> tuple[list[MatchedSegment], int]:
    """
    For each submission sentence, find the most similar paper abstract sentence.
    Returns (matched_segments, total_sentences_checked).
    """
    model = get_model()

    sub_sentences = split_sentences(submission_text)
    if not sub_sentences:
        return [], 0

    # Build reference corpus: split each abstract into sentences
    ref_sentences: list[str]       = []
    ref_paper_map: list[PaperSource] = []

    for paper in papers:
        abstract_sents = split_sentences(paper.abstract)
        for sent in abstract_sents:
            ref_sentences.append(sent)
            ref_paper_map.append(paper)

    if not ref_sentences:
        return [], len(sub_sentences)

    # Encode everything in two batch calls
    sub_embeddings = model.encode(sub_sentences,  convert_to_numpy=True, show_progress_bar=False)
    ref_embeddings = model.encode(ref_sentences,  convert_to_numpy=True, show_progress_bar=False)

    # (N_sub × N_ref) similarity matrix
    sim_matrix = cosine_similarity(sub_embeddings, ref_embeddings)

    matched: list[MatchedSegment] = []
    for i, sub_sent in enumerate(sub_sentences):
        best_idx   = int(np.argmax(sim_matrix[i]))
        best_score = float(sim_matrix[i][best_idx])

        if best_score >= threshold:
            start, end = find_char_positions(submission_text, sub_sent)
            matched.append(MatchedSegment(
                text           = sub_sent,
                start_char     = start,
                end_char       = end,
                similarity     = round(best_score, 4),
                similarity_pct = round(best_score * 100, 1),
                source         = ref_paper_map[best_idx],
            ))

    return matched, len(sub_sentences)


# ── Main entry point ──────────────────────────────────────────────────────────

async def check_academic_plagiarism(
    submission_text: str,
    threshold:       float = 0.75,
    top_k_queries:   int   = 5,
) -> AcademicCheckResult:
    """
    Full async pipeline:
      1. Extract query phrases
      2. Fetch papers concurrently
      3. Compute similarity
      4. Return structured result
    """
    t_start = time.time()

    # Step 1: Extract query phrases
    queries = extract_query_phrases(submission_text, n=3, top_k=top_k_queries)
    if not queries:
        queries = [submission_text[:100]]

    # Step 2: Fetch papers async (Semantic Scholar + ArXiv simultaneously)
    papers = await fetch_all_papers(queries)

    # Step 3: Compute matches
    matched_segments, sentences_checked = compute_matches(
        submission_text, papers, threshold=threshold
    )

    # Step 4: Aggregate score
    sub_sentences = split_sentences(submission_text)
    total = len(sub_sentences) if sub_sentences else 1
    overall_pct = round((len(matched_segments) / total) * 100, 1)

    return AcademicCheckResult(
        overall_similarity_pct = overall_pct,
        matched_segments       = matched_segments,
        sources_checked        = len(papers),
        sentences_checked      = sentences_checked,
        elapsed_seconds        = round(time.time() - t_start, 2),
        flagged                = overall_pct >= (threshold * 100),
    )


# ── JSON serialiser (for FastAPI response) ────────────────────────────────────

def result_to_json(result: AcademicCheckResult) -> dict:
    """Convert result to the JSON structure the frontend expects."""
    return {
        "overall_similarity_pct": result.overall_similarity_pct,
        "flagged":                result.flagged,
        "sources_checked":        result.sources_checked,
        "sentences_checked":      result.sentences_checked,
        "elapsed_seconds":        result.elapsed_seconds,
        "matched_segments": [
            {
                "text":           m.text,
                "start_char":     m.start_char,
                "end_char":       m.end_char,
                "similarity_pct": m.similarity_pct,
                "source": {
                    "title":   m.source.title,
                    "authors": m.source.authors,
                    "url":     m.source.url,
                    "year":    m.source.year,
                    "source":  m.source.source,
                },
            }
            for m in result.matched_segments
        ],
    }