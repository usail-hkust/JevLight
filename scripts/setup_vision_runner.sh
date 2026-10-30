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
RUNNER="$ROOT/.local/vision-runner/bin/python"
UV_PROJECT_ENVIRONMENT="$ROOT/.local/vision-runner" uv sync --locked --no-dev --extra sumo --python 3.12
# Renderer additions must not replace the benchmark's locked dependencies.
CONSTRAINTS="$ROOT/.local/vision-core-constraints.txt"
uv export --locked --no-dev --extra sumo --no-emit-project --no-hashes --output-file "$CONSTRAINTS" >/dev/null
uv pip install --python "$RUNNER" -c "$CONSTRAINTS" -r scripts/vision_runner_requirements.txt
uv pip check --python "$RUNNER"
sumo --version
# Fetch and verify the pinned renderer, including any files missing after interruption.
"$RUNNER" scripts/fetch_vlalight_renderer.py
