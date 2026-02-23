import numpy as np
from sqlalchemy import select
from app.models import Sentence
from app.database import SessionLocal

from app.utils.similarity_utils import (
    bert_cosine,
    tfidf_similarity,
    jaccard_similarity,
    hybrid_score
)

SIMILARITY_THRESHOLD = 0.65


def check_plagiarism(
    sentences,
    embeddings,
    assignment_group_id,
    current_student_id
):

    db = SessionLocal()

    total_sentences = len(sentences)
    plagiarized_count = 0
    matches = []

    for i in range(total_sentences):

        query_embedding = embeddings[i].tolist()

        # Get ALL sentences from other students in same assignment
        stmt = (
            select(Sentence)
            .where(
                Sentence.assignment_id == assignment_group_id,
                Sentence.student_id != current_student_id
            )
        )

        results = db.execute(stmt).scalars().all()

        if not results:
            continue

        best_match = None
        best_score = 0

        for result in results:

            bert_sim = bert_cosine(
                result.embedding,
                query_embedding
            )

            tfidf_sim = tfidf_similarity(
                sentences[i],
                result.sentence_text
            )

            jaccard_sim = jaccard_similarity(
                sentences[i],
                result.sentence_text
            )

            final_similarity = hybrid_score(
                bert_sim,
                tfidf_sim,
                jaccard_sim
            )

            if final_similarity > best_score:
                best_score = final_similarity
                best_match = result

        if best_score > SIMILARITY_THRESHOLD:

            plagiarized_count += 1

            matches.append({
                "input_sentence": sentences[i],
                "matched_sentence": best_match.sentence_text,
                "student_id": best_match.student_id,
                "final_similarity": float(best_score)
            })

    db.close()

    plagiarism_percentage = (
        (plagiarized_count / total_sentences) * 100
        if total_sentences > 0 else 0
    )

    return plagiarism_percentage, matches