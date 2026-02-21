import numpy as np
from sqlalchemy import select
from app.models import Sentence
from app.database import SessionLocal

SIMILARITY_THRESHOLD = 0.80

def check_plagiarism(sentences, embeddings, assignment_group_id, current_student_id):

    db = SessionLocal()
    total = len(sentences)
    plagiarized = 0
    matches = []

    for i in range(total):
        query_embedding = embeddings[i].tolist()

        stmt = (
            select(Sentence)
            .where(
                Sentence.assignment_id == assignment_group_id,
                Sentence.student_id != current_student_id
            )
            .order_by(
                Sentence.embedding.cosine_distance(query_embedding)
            )
            .limit(1)
        )

        result = db.execute(stmt).scalars().first()

        if result:
            # Cosine similarity = 1 - cosine_distance
            similarity = 1 - float(
                db.execute(
                    select(
                        Sentence.embedding.cosine_distance(query_embedding)
                    ).where(Sentence.id == result.id)
                ).scalar()
            )

            if similarity > SIMILARITY_THRESHOLD:
                plagiarized += 1
                matches.append({
                    "input_sentence": sentences[i],
                    "matched_sentence": result.sentence_text,
                    "student_id": result.student_id,
                    "similarity": similarity
                })

    db.close()

    plagiarism_percentage = (plagiarized / total) * 100 if total > 0 else 0

    return plagiarism_percentage, matches