#!/bin/sh
# Deploy the API and MCP server to a Hugging Face Docker Space.
#   uvx --from huggingface_hub hf auth login     # once, with a write token
#   deploy/hf_space.sh <owner>/isotherm
# Uploads only what the Dockerfile needs: no data, results, scripts or keys.
set -eu
HF="uvx --from huggingface_hub>=1 hf"
SPACE=${1:?usage: deploy/hf_space.sh <owner>/<space>}
cd "$(dirname "$0")/.."
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
mkdir -p "$OUT/shadow"
cp Dockerfile .dockerignore pyproject.toml uv.lock "$OUT/"
cp -R src "$OUT/src"
cp shadow/frozen.json "$OUT/shadow/frozen.json"
cp deploy/hf-space/README.md "$OUT/README.md"
find "$OUT" -name __pycache__ -type d -prune -exec rm -rf {} +
$HF repos create "$SPACE" --repo-type space --space-sdk docker --public --exist-ok
$HF upload "$SPACE" "$OUT" . --repo-type space --commit-message "Deploy $(git rev-parse --short HEAD)"
echo "https://huggingface.co/spaces/$SPACE"
