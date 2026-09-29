#!/bin/sh
set -e

MODEL_NAME="${MODEL_NAME:-}"
CACHE_DIR="${CACHE_DIR:-/cache/models}"
HF_TOKEN="${HF_TOKEN:-}"

if [ -z "$MODEL_NAME" ]; then
  echo "MODEL_NAME is not set. Skipping weight pre-load."
  exit 0
fi

MODEL_CACHE="$CACHE_DIR/$MODEL_NAME"

if [ -d "$MODEL_CACHE" ] && [ "$(ls -A "$MODEL_CACHE" 2>/dev/null)" ]; then
  echo "Weights already cached at $MODEL_CACHE"
  exit 0
fi

echo "Creating cache directory: $MODEL_CACHE"
mkdir -p "$MODEL_CACHE"

echo "Downloading model $MODEL_NAME to $MODEL_CACHE ..."
if [ -n "$HF_TOKEN" ]; then
  huggingface-cli download "$MODEL_NAME" --local-dir "$MODEL_CACHE" --token "$HF_TOKEN"
else
  huggingface-cli download "$MODEL_NAME" --local-dir "$MODEL_CACHE"
fi

echo "Model weights cached successfully at $MODEL_CACHE"