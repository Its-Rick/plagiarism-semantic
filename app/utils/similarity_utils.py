import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# -------- BERT COSINE --------
def bert_cosine(vec1, vec2):
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)

    return np.dot(vec1, vec2) / (
        np.linalg.norm(vec1) * np.linalg.norm(vec2)
    )


# -------- TFIDF COSINE --------
def tfidf_similarity(text1, text2):
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2)
    )

    vectors = vectorizer.fit_transform([text1, text2])
    return cosine_similarity(vectors[0], vectors[1])[0][0]


# -------- JACCARD --------
def jaccard_similarity(text1, text2):
    tokens1 = set(text1.lower().split())
    tokens2 = set(text2.lower().split())

    if not tokens1 and not tokens2:
        return 1.0

    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)

    return len(intersection) / len(union)


# -------- HYBRID --------
def hybrid_score(
    bert_score,
    tfidf_score,
    jaccard_score,
    w1=0.7,
    w2=0.2,
    w3=0.1
):
    return (w1 * bert_score) + (w2 * tfidf_score) + (w3 * jaccard_score)