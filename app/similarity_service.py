import faiss
import numpy as np
import os
import json

dimension = 384
INDEX_PATH = "storage/faiss.index"
METADATA_PATH = "storage/metadata.json"

# Initialize index
if os.path.exists(INDEX_PATH):
    index = faiss.read_index(INDEX_PATH)
else:
    index = faiss.IndexFlatIP(dimension)

# Load metadata
if os.path.exists(METADATA_PATH):
    with open(METADATA_PATH, "r") as f:
        stored_metadata = json.load(f)
else:
    stored_metadata = []

def normalize_vectors(vectors):
    faiss.normalize_L2(vectors)
    return vectors

def save_index():
    faiss.write_index(index, INDEX_PATH)

def save_metadata():
    with open(METADATA_PATH, "w") as f:
        json.dump(stored_metadata, f)

def add_embeddings(embeddings, metadata):
    embeddings = normalize_vectors(embeddings)
    index.add(embeddings)
    stored_metadata.extend(metadata)

    save_index()
    save_metadata()

def search_similar(query_embeddings, top_k=1):
    if index.ntotal == 0:
        return [], []

    query_embeddings = normalize_vectors(query_embeddings)
    scores, indices = index.search(query_embeddings, top_k)
    return scores, indices