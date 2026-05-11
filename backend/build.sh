#!/usr/bin/env bash
set -e

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Pre-downloading ONNX model..."
python - <<'PYEOF'
from huggingface_hub import snapshot_download
print("Downloading all-MiniLM-L6-v2 ONNX model...")
snapshot_download(
    repo_id="sentence-transformers/all-MiniLM-L6-v2",
    cache_dir="/opt/render/project/src/model_cache",
    ignore_patterns=["*.msgpack", "*.h5", "flax_model*", "tf_model*",
                     "pytorch_model*", "rust_model*"],
)
print("Model downloaded successfully.")
PYEOF

echo "==> Build complete."