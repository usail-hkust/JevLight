#!/usr/bin/env bash
# Shared simulation/renderer setup; does not load models or call the paid API.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"
export UV_CACHE_DIR="$ROOT/.local/uv-cache"
export PATH="$ROOT/.local/vision-runner/bin:$HOME/.local/bin:$PATH"
for tool in uv xvfb-run; do
  command -v "$tool" >/dev/null || { echo "Missing $tool; see docs/vision.md for installation." >&2; exit 1; }
done
if [[ ! -x .local/vision-runner/bin/python ]]; then
  uv venv --python 3.12 .local/vision-runner
fi
RUNNER="$ROOT/.local/vision-runner/bin/python"
uv pip install --python "$RUNNER" -r scripts/vision_runner_requirements.txt
sumo --version
# Fetch and verify the pinned renderer, including any files missing after interruption.
"$RUNNER" scripts/fetch_vlalight_renderer.py
