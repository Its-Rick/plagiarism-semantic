"""
academic_service.py — EduCheck Multi-Source Academic Plagiarism Checker
────────────────────────────────────────────────────────────────────────
5-stage pipeline:
  Stage 1 — Preprocessing      (utils.py)
  Stage 2 — Parallel retrieval (arXiv + OpenAlex + GitHub via asyncio)
  Stage 3 — Text processing    (split + clean retrieved content)
  Stage 4 — Semantic similarity (all-MiniLM-L6-v2 via ONNX, batched)
  Stage 5 — Scoring            (flagged / total x 100)
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import aiohttp
import numpy as np

from .utils import split_sentences, extract_keywords, clean_abstract, truncate
from app.services.embedding_service import generate_embeddings

# ── Constants ─────────────────────────────────────────────────────────────────
# Tune these down to stay under 512MB on Render free tier
MAX_SOURCES       = 15   # cap total papers fetched
MAX_REF_SENTENCES = 200  # cap reference corpus size
ENCODE_BATCH      = 32   # sentences per ONNX batch


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class SourceDocument:
    title:  str
    text:   str
    url:    str
    source: str
    year:   Optional[int] = None


@dataclass
class MatchResult:
    input_sentence:   str
    matched_sentence: str
    source:           str
    similarity:       float
    similarity_pct:   float
    title:            str
    url:              str


@dataclass
class AcademicCheckResult:
    plagiarism_percentage: float
    matches:               List[MatchResult]
    sources_checked:       int
    sentences_checked:     int
    elapsed_seconds:       float
    flagged:               bool


_HEADERS = {"User-Agent": "EduCheck-Academic-Checker/2.0 (educational plagiarism detection)"}


# ── Stage 2a: arXiv ───────────────────────────────────────────────────────────

async def _fetch_arxiv(session: aiohttp.ClientSession, query: str, limit: int = 3) -> List[SourceDocument]:
    url = "http://export.arxiv.org/api/query"
    params = {"search_query": f"all:{query}", "max_results": limit, "sortBy": "relevance"}
    docs: List[SourceDocument] = []
    try:
        async with session.get(url, params=params, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return docs
            raw = await resp.text()
        for entry in re.findall(r'<entry>(.*?)</entry>', raw, re.DOTALL):
            title_m   = re.search(r'<title>(.*?)</title>',     entry, re.DOTALL)
            summary_m = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
            link_m    = re.search(r'<id>(.*?)</id>',           entry)
            year_m    = re.search(r'<published>(\d{4})',       entry)
            abstract  = clean_abstract(summary_m.group(1).strip() if summary_m else "")
            if len(abstract) < 30:
                continue
            docs.append(SourceDocument(
                title  = (title_m.group(1).strip() if title_m else "Untitled").replace("\n", " "),
                text   = abstract,
                url    = (link_m.group(1).strip() if link_m else ""),
                source = "arXiv",
                year   = (int(year_m.group(1)) if year_m else None),
            ))
    except Exception as e:
        print(f"[arXiv] '{query}': {e}")
    return docs


# ── Stage 2b: OpenAlex ────────────────────────────────────────────────────────

def _reconstruct_abstract(inv_idx: dict) -> str:
    if not inv_idx:
        return ""
    pairs: List[Tuple[int, str]] = []
    for word, positions in inv_idx.items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort(key=lambda x: x[0])
    return " ".join(w for _, w in pairs)


async def _fetch_openalex(session: aiohttp.ClientSession, query: str, limit: int = 3) -> List[SourceDocument]:
    url    = "https://api.openalex.org/works"
    params = {
        "search":   query,
        "per-page": limit,
        "select":   "title,abstract_inverted_index,doi,publication_year,primary_location",
        "mailto":   "educheck@example.com",
    }
    docs: List[SourceDocument] = []
    try:
        async with session.get(url, params=params, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return docs
            data = await resp.json()
        for work in data.get("results", []):
            abstract = clean_abstract(_reconstruct_abstract(work.get("abstract_inverted_index") or {}))
            if len(abstract) < 30:
                continue
            doi      = work.get("doi") or ""
            work_url = ((work.get("primary_location") or {}).get("landing_page_url")
                        or (f"https://doi.org/{doi}" if doi else ""))
            docs.append(SourceDocument(
                title  = work.get("title") or "Untitled",
                text   = abstract,
                url    = work_url,
                source = "OpenAlex",
                year   = work.get("publication_year"),
            ))
    except Exception as e:
        print(f"[OpenAlex] '{query}': {e}")
    return docs


# ── Stage 2c: GitHub ──────────────────────────────────────────────────────────

async def _fetch_github(session: aiohttp.ClientSession, query: str, limit: int = 2) -> List[SourceDocument]:
    url     = "https://api.github.com/search/repositories"
    params  = {"q": query, "sort": "stars", "order": "desc", "per_page": limit}
    headers = {**_HEADERS}
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"
    docs: List[SourceDocument] = []
    try:
        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 403:
                print("[GitHub] Rate limited — set GITHUB_TOKEN env var")
                return docs
            if resp.status != 200:
                return docs
            data = await resp.json()
        for repo in data.get("items", []):
            description = repo.get("description") or ""
            topics      = " ".join(repo.get("topics") or [])
            language    = repo.get("language") or ""
            parts       = [p for p in [description, topics, language] if p]
            combined    = " | ".join(parts)
            if len(combined) < 20:
                continue
            docs.append(SourceDocument(
                title  = repo.get("full_name", ""),
                text   = combined,
                url    = repo.get("html_url", ""),
                source = "GitHub",
            ))
    except Exception as e:
        print(f"[GitHub] '{query}': {e}")
    return docs


# ── Stage 2: Parallel orchestrator ───────────────────────────────────────────

async def _fetch_all_sources(keywords: List[str]) -> List[SourceDocument]:
    # Use only top 3 keywords to limit API calls and corpus size
    top_keywords = keywords[:3]
    async with aiohttp.ClientSession() as session:
        tasks = []
        for kw in top_keywords:
            tasks.append(_fetch_arxiv(session, kw, limit=3))
            tasks.append(_fetch_openalex(session, kw, limit=3))
            tasks.append(_fetch_github(session, kw, limit=2))
        batches = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set = set()
    docs: List[SourceDocument] = []
    for batch in batches:
        if isinstance(batch, Exception):
            continue
        for doc in batch:
            if len(docs) >= MAX_SOURCES:
                break
            key = hashlib.md5(doc.title.lower().encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                docs.append(doc)

    arxiv_n    = sum(1 for d in docs if d.source == "arXiv")
    openalex_n = sum(1 for d in docs if d.source == "OpenAlex")
    github_n   = sum(1 for d in docs if d.source == "GitHub")
    print(f"[retrieval] {len(docs)} sources — arXiv:{arxiv_n} OpenAlex:{openalex_n} GitHub:{github_n}")
    return docs


# ── Stage 3: Build reference corpus ──────────────────────────────────────────

def _build_corpus(docs: List[SourceDocument]) -> Tuple[List[str], List[SourceDocument]]:
    ref_sentences: List[str] = []
    ref_doc_map: List[SourceDocument] = []
    for doc in docs:
        for sent in split_sentences(truncate(doc.text, 1000)):  # shorter truncation
            if len(ref_sentences) >= MAX_REF_SENTENCES:
                break
            ref_sentences.append(sent)
            ref_doc_map.append(doc)
        if len(ref_sentences) >= MAX_REF_SENTENCES:
            break
    return ref_sentences, ref_doc_map


# ── Stage 4: Batched encoding ─────────────────────────────────────────────────

def _encode_batched(sentences: List[str], batch_size: int = ENCODE_BATCH) -> np.ndarray:
    """Encode in small batches to keep peak memory flat."""
    if not sentences:
        return np.empty((0, 384), dtype="float32")
    parts = []
    for i in range(0, len(sentences), batch_size):
        parts.append(generate_embeddings(sentences[i : i + batch_size]))
    return np.vstack(parts)


# ── Stage 5: Memory-efficient similarity + scoring ───────────────────────────

def _compute_matches(
    submission_text: str,
    ref_sentences:   List[str],
    ref_doc_map:     List[SourceDocument],
    threshold:       float,
) -> Tuple[List[MatchResult], int]:
    sub_sentences = split_sentences(submission_text)
    if not sub_sentences or not ref_sentences:
        return [], len(sub_sentences) if sub_sentences else 0

    # Encode reference corpus once
    ref_emb = _encode_batched(ref_sentences)

    matches: List[MatchResult] = []

    # Encode and score submission sentences one batch at a time
    # so we never hold sub_emb @ ref_emb for the full matrix simultaneously
    for i in range(0, len(sub_sentences), ENCODE_BATCH):
        batch_sents = sub_sentences[i : i + ENCODE_BATCH]
        batch_emb   = _encode_batched(batch_sents, batch_size=ENCODE_BATCH)
        sim_block   = batch_emb @ ref_emb.T   # (batch, N_ref) — small slice only

        for j, sub_sent in enumerate(batch_sents):
            best_j     = int(np.argmax(sim_block[j]))
            best_score = float(sim_block[j][best_j])
            if best_score >= threshold:
                doc = ref_doc_map[best_j]
                matches.append(MatchResult(
                    input_sentence   = sub_sent,
                    matched_sentence = ref_sentences[best_j],
                    source           = doc.source,
                    similarity       = round(best_score, 4),
                    similarity_pct   = round(best_score * 100, 1),
                    title            = doc.title,
                    url              = doc.url,
                ))

        del sim_block, batch_emb  # free immediately after each block

    return matches, len(sub_sentences)


# ── Public entry point ────────────────────────────────────────────────────────

async def check_academic_plagiarism(
    submission_text: str,
    threshold:       float = 0.65,
    top_k_keywords:  int   = 8,
) -> AcademicCheckResult:
    t_start  = time.time()
    keywords = extract_keywords(submission_text, top_k=top_k_keywords)
    print(f"[pipeline] Keywords: {keywords}")

    docs                       = await _fetch_all_sources(keywords)
    ref_sentences, ref_doc_map = _build_corpus(docs)
    print(f"[pipeline] Corpus: {len(ref_sentences)} ref sentences from {len(docs)} sources")

    matches, total = _compute_matches(submission_text, ref_sentences, ref_doc_map, threshold)
    plag_pct = round((len(matches) / max(total, 1)) * 100, 1)
    elapsed  = round(time.time() - t_start, 2)
    print(f"[pipeline] {plag_pct}% ({len(matches)}/{total} sentences) in {elapsed}s")

    return AcademicCheckResult(
        plagiarism_percentage = plag_pct,
        matches               = matches,
        sources_checked       = len(docs),
        sentences_checked     = total,
        elapsed_seconds       = elapsed,
        flagged               = plag_pct >= (threshold * 100),
    )


# ── JSON serialiser ───────────────────────────────────────────────────────────

def result_to_json(result: AcademicCheckResult) -> dict:
    segments = [
        {
            "text":           m.input_sentence,
            "start_char":     0,
            "end_char":       len(m.input_sentence),
            "similarity_pct": m.similarity_pct,
            "source": {"title": m.title, "authors": [], "url": m.url, "year": None, "source": m.source},
        }
        for m in result.matches
    ]
    return {
        "plagiarism_percentage":  result.plagiarism_percentage,
        "overall_similarity_pct": result.plagiarism_percentage,
        "flagged":                result.flagged,
        "sources_checked":        result.sources_checked,
        "sentences_checked":      result.sentences_checked,
        "elapsed_seconds":        result.elapsed_seconds,
        "matched_segments":       segments,
        "matches": [
            {
                "input_sentence":   m.input_sentence,
                "matched_sentence": m.matched_sentence,
                "source":           m.source,
                "similarity":       m.similarity,
                "similarity_pct":   m.similarity_pct,
                "title":            m.title,
                "url":              m.url,
            }
            for m in result.matches
        ],
    }