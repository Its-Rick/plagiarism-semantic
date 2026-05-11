"""
embedding_service.py
Runs all-MiniLM-L6-v2 via ONNX. Model is pre-downloaded during build.
"""

import numpy as np
from pathlib import Path
from huggingface_hub import snapshot_download
from tokenizers import Tokenizer
import onnxruntime as ort

MODEL_ID   = "sentence-transformers/all-MiniLM-L6-v2"
CACHE_DIR  = "/opt/render/project/src/model_cache"

def _load_model():
    # Use pre-downloaded cache — no network call at runtime
    model_dir = snapshot_download(
        repo_id=MODEL_ID,
        cache_dir=CACHE_DIR,
        local_files_only=True,   # ← never hits network at runtime
        ignore_patterns=["*.msgpack", "*.h5", "flax_model*", "tf_model*",
                         "pytorch_model*", "rust_model*"],
    )
    onnx_path      = Path(model_dir) / "onnx" / "model.onnx"
    tokenizer_path = Path(model_dir) / "tokenizer.json"

    session = ort.InferenceSession(
        str(onnx_path),
        providers=["CPUExecutionProvider"],
    )
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.enable_padding(pad_token="[PAD]", pad_id=0)
    tokenizer.enable_truncation(max_length=256)

    return session, tokenizer

_session, _tokenizer = _load_model()

def _mean_pool(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    mask = attention_mask[..., np.newaxis].astype(float)
    return (token_embeddings * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1e-9)

def generate_embeddings(sentences: list[str]) -> np.ndarray:
    if not sentences:
        return np.empty((0, 384), dtype="float32")

    encoded        = _tokenizer.encode_batch(sentences)
    input_ids      = np.array([e.ids            for e in encoded], dtype="int64")
    attention_mask = np.array([e.attention_mask for e in encoded], dtype="int64")
    token_type_ids = np.zeros_like(input_ids,                      dtype="int64")

    outputs = _session.run(None, {
        "input_ids":      input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": token_type_ids,
    })

    pooled = _mean_pool(outputs[0], attention_mask)
    norms  = np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
    return (pooled / norms).astype("float32")