from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")

def generate_embeddings(sentences):
    embeddings = model.encode(sentences)
    return np.array(embeddings).astype("float32")