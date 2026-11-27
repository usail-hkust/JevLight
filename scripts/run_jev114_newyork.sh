#!/usr/bin/env bash
# Run only the unrun hosted Jev 1.14.0 visual experiments on New York (flows 1-2, seeds 1-3),
# aligned with official_vision_20261106_sumo128_v5 (SUMO 1.28.0, vlalight-two-stage-v2-co,
# upstream-3600s-15s-visual-v3, --checkpoint-every-steps 8, --resume, zero fallbacks).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/scripts/run_fair_vision_matrix.py" ]]; then
  ROOT="$SCRIPT_DIR"
elif [[ -f "$SCRIPT_DIR/../scripts/run_fair_vision_matrix.py" ]]; then
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
elif [[ -f "$PWD/scripts/run_fair_vision_matrix.py" ]]; then
  ROOT="$PWD"
else
  echo "Error: Place this script in the JevLight repository root or inside scripts/." >&2
  exit 1
fi
cd "$ROOT"

FLOWS=(newyork-1 newyork-2)
SEEDS=(1 2 3)
CHECKPOINT_EVERY=8
OUTPUT="results/official_vision_newyork_jev114"
EXECUTE=1
SKIP_SETUP=0
USE_XVFB=1
LIMIT=""

usage() {
  cat <<'EOF'
Usage: bash scripts/run_jev114_newyork.sh [options]

Runs only the missing New York hosted Jev 1.14.0 visual experiments
(newyork-1, newyork-2; seeds 1, 2, 3) with exact alignment to the
official_vision_20261106_sumo128_v5 Jinan/Hangzhou batch.

Options:
  --flows FLOW...               Override flows (default: newyork-1 newyork-2)
  --seeds SEED...               Override seeds from {1,2,3} (default: 1 2 3)
  --limit N                     Run at most N pending conditions
  --checkpoint-every-steps N    Checkpoint interval in control steps (default: 8)
  --output PATH                 Output directory under results/ (default: results/official_vision_newyork_jev114)
  --plan-only, --dry-run        Write/verify plan.json without calling API or SUMO
  --skip-setup                  Reuse existing .local/vision-runner without running setup_vision_runner.sh
  --no-xvfb                     Run directly without xvfb-run
  -h, --help                    Show this help message

Credentials:
  Export TYPESAFE_API_KEY (or JEV_API_KEY_POOL) before running without --plan-only.
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --flows)
      shift
      FLOWS=()
      while [[ "$#" -gt 0 && "$1" != -* ]]; do
        FLOWS+=("$1")
        shift
      done
      [[ "${#FLOWS[@]}" -gt 0 ]] || { echo "Error: --flows requires at least one flow." >&2; exit 2; }
      ;;
    --seeds)
      shift
      SEEDS=()
      while [[ "$#" -gt 0 && "$1" != -* ]]; do
        SEEDS+=("$1")
        shift
      done
      [[ "${#SEEDS[@]}" -gt 0 ]] || { echo "Error: --seeds requires at least one seed." >&2; exit 2; }
      ;;
    --limit)
      [[ "$#" -ge 2 ]] || { echo "Error: --limit requires an integer." >&2; exit 2; }
      LIMIT="$2"
      shift 2
      ;;
    --checkpoint-every-steps)
      [[ "$#" -ge 2 ]] || { echo "Error: --checkpoint-every-steps requires an integer." >&2; exit 2; }
      CHECKPOINT_EVERY="$2"
      shift 2
      ;;
    --output)
      [[ "$#" -ge 2 ]] || { echo "Error: --output requires a path." >&2; exit 2; }
      OUTPUT="$2"
      shift 2
      ;;
    --plan-only|--dry-run)
      EXECUTE=0
      shift
      ;;
    --skip-setup)
      SKIP_SETUP=1
      shift
      ;;
    --no-xvfb)
      USE_XVFB=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

export PYTHONUNBUFFERED=1
# Prevent a community MCP key from overriding TYPESAFE_API_KEY in jevlight/jev_client.py.
unset JEV_API_KEY

if [[ "$EXECUTE" -eq 1 && -z "${TYPESAFE_API_KEY:-}" && -z "${JEV_API_KEY_POOL:-}" ]]; then
  echo "Error: Set TYPESAFE_API_KEY (or JEV_API_KEY_POOL) before executing paid Jev 1.14.0 runs." >&2
  echo "Tip: Pass --plan-only to verify configuration hashes without calling the API." >&2
  exit 1
fi

RUNNER=""
if [[ -x "$ROOT/.local/vision-runner/bin/python" ]]; then
  RUNNER="$ROOT/.local/vision-runner/bin/python"
elif [[ -x "$ROOT/.local/vision-runner/Scripts/python.exe" ]]; then
  RUNNER="$ROOT/.local/vision-runner/Scripts/python.exe"
fi

if [[ -z "$RUNNER" ]]; then
  if [[ "$SKIP_SETUP" -eq 1 ]]; then
    echo "Error: .local/vision-runner not found and --skip-setup was set." >&2
    exit 1
  fi
  bash scripts/setup_vision_runner.sh
  if [[ -x "$ROOT/.local/vision-runner/bin/python" ]]; then
    RUNNER="$ROOT/.local/vision-runner/bin/python"
  elif [[ -x "$ROOT/.local/vision-runner/Scripts/python.exe" ]]; then
    RUNNER="$ROOT/.local/vision-runner/Scripts/python.exe"
  else
    echo "Error: Failed to locate python inside .local/vision-runner after setup." >&2
    exit 1
  fi
elif [[ "$SKIP_SETUP" -eq 0 && "$EXECUTE" -eq 1 ]]; then
  # Ensure pinned SUMO 1.28.0 and renderer assets match before starting paid runs.
  "$RUNNER" -c 'from jevlight.sumo_runtime import require_sumo_128; require_sumo_128()'
  "$RUNNER" scripts/fetch_vlalight_renderer.py
fi

PREFIX=()
if [[ "$EXECUTE" -eq 1 && "$USE_XVFB" -eq 1 ]]; then
  if command -v xvfb-run >/dev/null 2>&1; then
    PREFIX=(xvfb-run -a)
  elif [[ "$(uname -s)" == Linux* && -z "${DISPLAY:-}" ]]; then
    echo "Error: xvfb-run not found and DISPLAY is unset on Linux; install xvfb or pass --no-xvfb." >&2
    exit 1
  fi
fi

EXTRA_ARGS=()
if [[ "$EXECUTE" -eq 1 ]]; then
  EXTRA_ARGS+=(--execute --resume)
  if [[ -n "$LIMIT" ]]; then
    EXTRA_ARGS+=(--limit "$LIMIT")
  fi
fi

${PREFIX[@]+"${PREFIX[@]}"} "$RUNNER" scripts/run_fair_vision_matrix.py   --models jev-vision   --flows "${FLOWS[@]}"   --seeds "${SEEDS[@]}"   --checkpoint-every-steps "$CHECKPOINT_EVERY"   --output "$OUTPUT"   ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}

if [[ "$EXECUTE" -eq 1 ]]; then
  "$RUNNER" - "$OUTPUT" <<'PY'
import json
import sys
from pathlib import Path

scores_path = Path(sys.argv[1]) / "formal" / "scores.json"
if not scores_path.is_file():
    print(f"No scores.json written at {scores_path}")
    raise SystemExit(0)
scores = json.loads(scores_path.read_text(encoding="utf-8"))
print("\n=== Jev 1.14.0 New York Summary ===")
for key in sorted(scores):
    if not key.startswith("jev-vision/newyork-"):
        continue
    entry = scores[key]
    m = entry["metrics"]
    awt = m["avg_waiting_time"]
    att = m["avg_travel_time"]
    aql = m["avg_queue_len"]
    fmt = lambda s: f"{s['mean']:.1f}+/-{s['sample_std']:.1f}" if s["sample_std"] is not None else f"{s['mean']:.1f}"
    print(f"{key} seeds={entry['seeds']}: AWT={fmt(awt)} s, ATT={fmt(att)} s, AQL={fmt(aql)}")
PY
fi
