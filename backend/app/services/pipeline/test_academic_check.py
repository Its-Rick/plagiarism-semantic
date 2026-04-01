"""
test_academic_check.py — Example test cases for the academic check pipeline.

Run from the backend/ directory:
    pytest app/services/pipeline/test_academic_check.py -v -s

Or test the live endpoint:
    python app/services/pipeline/test_academic_check.py
"""

import asyncio
import pytest

# ── Example texts for testing ─────────────────────────────────────────────────

SAMPLE_ORIGINAL = """
Machine learning has revolutionized the way we approach complex problems.
Neural networks have shown remarkable performance across many domains including
image recognition, natural language processing, and game playing.
Deep learning models trained on large datasets can generalize well to unseen data.
"""

SAMPLE_ACADEMIC = """
Transformer models have become the dominant architecture in natural language processing.
The attention mechanism allows models to capture long-range dependencies in sequences.
Pre-trained language models such as BERT and GPT have achieved state-of-the-art results
on a wide variety of downstream NLP tasks including text classification and question answering.
Transfer learning from large pre-trained models has significantly reduced the need for
task-specific labeled data in many machine learning applications.
"""

SAMPLE_CS_CODE = """
Convolutional neural networks use gradient descent optimization to minimize the loss function.
Backpropagation computes gradients efficiently through the chain rule of calculus.
Batch normalization helps stabilize training by normalizing layer inputs.
Dropout is a regularization technique that randomly deactivates neurons during training.
The softmax function converts raw model outputs into probability distributions.
"""

SAMPLE_SHORT = "This text is too short."

# ── Unit tests ────────────────────────────────────────────────────────────────

class TestUtils:
    def test_split_sentences(self):
        from app.services.pipeline.utils import split_sentences
        sents = split_sentences(SAMPLE_ACADEMIC)
        assert len(sents) >= 4, "Should split into multiple sentences"
        assert all(len(s) >= 20 for s in sents), "All sentences should be >= 20 chars"

    def test_extract_keywords(self):
        from app.services.pipeline.utils import extract_keywords
        kws = extract_keywords(SAMPLE_ACADEMIC, top_k=6)
        assert len(kws) >= 3, "Should extract at least 3 keywords"
        assert all(isinstance(k, str) for k in kws)
        print(f"\nKeywords from academic text: {kws}")

    def test_normalize_text(self):
        from app.services.pipeline.utils import normalize_text
        norm = normalize_text("The Quick Brown Fox! Jumps over the lazy dog.")
        assert "the" not in norm.split(), "Stopwords should be removed"
        assert norm == norm.lower(), "Should be lowercase"

    def test_clean_abstract(self):
        from app.services.pipeline.utils import clean_abstract
        latex = r"We propose $\mathcal{L}$ loss with \textbf{attention}."
        cleaned = clean_abstract(latex)
        assert "$" not in cleaned
        assert "\\" not in cleaned


class TestPipeline:
    """Integration tests — hit live APIs (require network)."""

    @pytest.mark.asyncio
    async def test_full_pipeline_academic(self):
        from app.services.pipeline.academic_service import check_academic_plagiarism
        result = await check_academic_plagiarism(SAMPLE_ACADEMIC, threshold=0.65)

        print(f"\n--- Academic text result ---")
        print(f"Plagiarism: {result.plagiarism_percentage}%")
        print(f"Sources checked: {result.sources_checked}")
        print(f"Sentences checked: {result.sentences_checked}")
        print(f"Matches: {len(result.matches)}")
        print(f"Time: {result.elapsed_seconds}s")
        if result.matches:
            m = result.matches[0]
            print(f"Top match [{m.source}] {m.similarity_pct}%: {m.title[:60]}")

        assert result.sentences_checked >= 3
        assert result.sources_checked >= 0    # may be 0 if network unavailable
        assert 0.0 <= result.plagiarism_percentage <= 100.0

    @pytest.mark.asyncio
    async def test_full_pipeline_cs(self):
        from app.services.pipeline.academic_service import check_academic_plagiarism
        result = await check_academic_plagiarism(SAMPLE_CS_CODE, threshold=0.65)

        print(f"\n--- CS text result ---")
        print(f"Plagiarism: {result.plagiarism_percentage}%")
        print(f"Sources: {result.sources_checked} | Matches: {len(result.matches)}")
        for m in result.matches[:3]:
            print(f"  [{m.source}] {m.similarity_pct}% — {m.title[:50]}")

        assert 0.0 <= result.plagiarism_percentage <= 100.0

    @pytest.mark.asyncio
    async def test_empty_sources_handled(self):
        """Pipeline should handle 0 sources gracefully without crashing."""
        from app.services.pipeline.academic_service import _compute_matches
        matches, total = _compute_matches(SAMPLE_ORIGINAL, [], [], threshold=0.65)
        assert matches == []
        assert total >= 0

    @pytest.mark.asyncio
    async def test_result_to_json(self):
        from app.services.pipeline.academic_service import check_academic_plagiarism, result_to_json
        result = await check_academic_plagiarism(SAMPLE_ACADEMIC, threshold=0.65)
        j = result_to_json(result)

        # Check all required keys present
        assert "plagiarism_percentage"  in j
        assert "matches"                in j
        assert "matched_segments"       in j   # legacy alias
        assert "overall_similarity_pct" in j   # legacy alias
        assert "sources_checked"        in j
        assert "elapsed_seconds"        in j

        if j["matches"]:
            m = j["matches"][0]
            assert "input_sentence"   in m
            assert "matched_sentence" in m
            assert "source"           in m
            assert "similarity"       in m
            assert "title"            in m


# ── CLI quick-test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    # Make sure we can import from backend/
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

    from app.services.pipeline.academic_service import check_academic_plagiarism, result_to_json
    import json

    async def main():
        print("=" * 60)
        print("EduCheck — Academic Check Pipeline Test")
        print("=" * 60)

        text = SAMPLE_ACADEMIC
        print(f"\nInput ({len(text)} chars):\n{text.strip()}\n")

        result = await check_academic_plagiarism(text, threshold=0.65)
        output = result_to_json(result)

        print(f"\n{'='*60}")
        print(f"Plagiarism score : {output['plagiarism_percentage']}%")
        print(f"Sources checked  : {output['sources_checked']}")
        print(f"Sentences checked: {output['sentences_checked']}")
        print(f"Elapsed          : {output['elapsed_seconds']}s")
        print(f"Flagged          : {output['flagged']}")
        print(f"\nMatches ({len(output['matches'])}):")
        for i, m in enumerate(output["matches"], 1):
            print(f"  {i}. [{m['source']}] {m['similarity_pct']}% — {m['title'][:55]}")
            print(f"     Input  : {m['input_sentence'][:80]}")
            print(f"     Matched: {m['matched_sentence'][:80]}")

    asyncio.run(main())