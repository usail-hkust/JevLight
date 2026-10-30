#!/usr/bin/env bash
# Ubuntu 24.04, one full 80/96 GB NVIDIA GPU. Models run serially.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
MODE=run
MODELS=()
usage() {
  echo 'Usage: bash scripts/run_vision_server.sh [--mode setup|run] [--models wemm-jev d3-turbo amos-1-large]'
}
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ "$#" -ge 2 ]] || { usage >&2; exit 2; }
      MODE="$2"; shift 2 ;;
    --models)
      shift
      [[ "$#" -gt 0 && "$1" != -* ]] || { usage >&2; exit 2; }
      while [[ "$#" -gt 0 && "$1" != -* ]]; do MODELS+=("$1"); shift; done ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ "$MODE" == run || "$MODE" == setup ]] || { usage >&2; exit 2; }
if [[ "${#MODELS[@]}" -eq 0 ]]; then MODELS=(wemm-jev d3-turbo amos-1-large); fi
if [[ -z "${JEVLIGHT_VISION_LOCK_FD:-}" ]]; then
  exec python3 -m scripts.vision_server_job --mode "$MODE" --models "${MODELS[@]}"
fi
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_XET=1
export UV_CACHE_DIR="$ROOT/.local/uv-cache"
export NO_PROXY="localhost,127.0.0.1,::1${NO_PROXY:+,$NO_PROXY}${no_proxy:+,$no_proxy}"
export no_proxy="$NO_PROXY"
export PATH="$ROOT/.local/vision-runner/bin:$HOME/.local/bin:$PATH"
# Check before downloading weights or installing large GPU environments.
python3 - "${MODELS[@]}" <<'PY'
import json, os, shutil, subprocess, sys
from pathlib import Path
specs = json.load(open('config/vision_models.json'))
selected = sys.argv[1:]
unknown = sorted(set(selected) - specs.keys())
if unknown or len(selected) != len(set(selected)):
    raise SystemExit(f'Select unique model keys from {", ".join(specs)}; got {selected}')
devices = os.environ.get('CUDA_VISIBLE_DEVICES')
query = ['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits']
if devices is not None:
    if not devices or ',' in devices:
        raise SystemExit('Set CUDA_VISIBLE_DEVICES to one GPU index or UUID.')
    query.extend(['-i', devices])
rows = subprocess.check_output(query, text=True)
free = [int(x.strip()) for x in rows.splitlines() if x.strip()]
if len(free) != 1 or free[0] < 70 * 1024:
    raise SystemExit('Expose exactly one NVIDIA GPU with at least 70 GiB free VRAM; prefer RTX PRO 6000 96 GB.')
missing = sum(not Path('.local/vision-models', key, 'jevlight-download.json').is_file() for key in selected)
if os.environ.get('JEVLIGHT_RELEASE_COMPLETED_MODELS') == '1':
    # Reserve each checkpoint below, after completed models have been released.
    missing = 0
needed = 40 + 65 * missing
available = shutil.disk_usage('.').free / 1024**3
if available < needed:
    raise SystemExit(f'Need {needed} GiB free disk to prepare {", ".join(selected)}; available {available:.1f} GiB. '
                     'Select one model to reduce checkpoint storage, or expand the data disk. '
                     'This startup check does not reserve space for all saved experiment frames.')
print(f'Selected models: {", ".join(selected)}; disk available {available:.1f} GiB, startup minimum {needed} GiB.', flush=True)
with open('/proc/meminfo') as f:
    mem = {line.split(':')[0]: int(line.split()[1]) for line in f}
if mem['MemTotal'] < 120 * 1024**2:
    raise SystemExit('Select a server with at least 128 GB system RAM.')
PY

python3 scripts/vision_server_network.py "${MODELS[@]}"

source scripts/setup_vision_runner.sh
mkdir -p .local/vision-models results/vision_server logs/vision_server
for key in "${MODELS[@]}"; do
  ENV="$ROOT/.local/vision-$key"
  WEIGHTS="$ROOT/.local/vision-models/$key"
  if [[ "$MODE" == run && "${JEVLIGHT_RELEASE_COMPLETED_MODELS:-0}" == 1 ]]; then
    COMPLETE=$("$RUNNER" - "$key" <<'PY'
import sys
from scripts.vision_server_storage import completed, release
if completed(sys.argv[1]):
    release(sys.argv[1])
    print('yes')
else:
    print('no')
PY
)
    if [[ "$COMPLETE" == yes ]]; then
      echo "Reusing all 21 validated conditions for $key; skipping download and inference."
      uv cache clean
      continue
    fi
  fi
  "$RUNNER" - "$key" <<'PY'
import shutil, sys
from pathlib import Path
cached = Path('.local/vision-models', sys.argv[1], 'jevlight-download.json').is_file()
needed = 40 if cached else 105
available = shutil.disk_usage('.').free / 1024**3
if available < needed:
    raise SystemExit(f'Need {needed} GiB free before preparing {sys.argv[1]}; available {available:.1f} GiB. '
                     'Prior results are preserved; expand the data disk before resuming.')
PY
  if [[ ! -x "$ENV/bin/python" ]]; then uv venv --python 3.12 "$ENV"; fi
  PY="$ENV/bin/python"
  uv pip install --python "$PY" huggingface-hub==1.33.0
  # Small author sources first; each model keeps its own dependency environment.
  "$PY" -m scripts.vision_server_download "$key" "$WEIGHTS" sources
  if [[ "$key" == wemm-jev ]]; then
    uv pip install --python "$PY" -r "$WEIGHTS/inference/requirements.txt"
    # The author's CUDA recipe explicitly upgrades Triton without changing torch.
    uv pip install --python "$PY" --no-deps 'triton>=3.7.1,<3.8'
  elif [[ "$key" == amos-1-large ]]; then
    uv pip install --python "$PY" "$WEIGHTS/serve" torchvision==0.29.0
  else
    uv pip install --python "$PY" torch==2.14.0 torchvision==0.29.0 transformers==5.17.0 \
      pillow==12.3.0 safetensors==0.8.0 accelerate==1.15.0 opencv-python-headless flash-linear-attention==0.5.2
  fi
  "$PY" -m scripts.vision_server_download "$key" "$WEIGHTS" full
  if [[ "$key" == wemm-jev ]]; then
    if ! "$PY" -c 'import causal_conv1d' >/dev/null 2>&1; then
      WHEEL='https://github.com/Dao-AILab/causal-conv1d/releases/download/v1.7.0/causal_conv1d-1.7.0+cu12torch2.8cxx11abiTRUE-cp312-cp312-linux_x86_64.whl'
      uv pip install --python "$PY" --no-deps "$WHEEL"
    fi
    "$PY" scripts/check_wemm_cuda.py --output "results/vision_server/wemm-cuda-$(date +%Y%m%d-%H%M%S).json"
  fi
  uv pip freeze --python "$PY" > "results/vision_server/environment-$key.txt"
  [[ "$MODE" == setup ]] && continue
  "$PY" scripts/serve_vision_model.py --model "$key" --weights "$WEIGHTS" \
      > "logs/vision_server/$key.log" 2>&1 &
  SERVICE_PID=$!
  cleanup() { kill "$SERVICE_PID" 2>/dev/null || true; wait "$SERVICE_PID" 2>/dev/null || true; }
  trap cleanup EXIT
  "$RUNNER" - "$key" "$SERVICE_PID" <<'PY'
import json, os, sys, time
import requests
spec = json.load(open('config/vision_models.json'))[sys.argv[1]]
for attempt in range(1800):
    try:
        os.kill(int(sys.argv[2]), 0)
    except ProcessLookupError:
        raise SystemExit('Model service exited; inspect logs/vision_server/' + sys.argv[1] + '.log')
    try:
        r = requests.get('http://127.0.0.1:8123/health', timeout=2)
        r.raise_for_status()
        info = r.json()
        if info.get('model') != spec['model_id'] or info.get('revision') != spec['revision']:
            raise SystemExit('Port 8123 belongs to a different model/revision. Stop the existing service.')
        break
    except requests.RequestException:
        time.sleep(2)
else:
    raise SystemExit('Model startup timed out; see its service log.')
PY
  # The matrix checks the image API contract before starting formal simulations.
  xvfb-run -a "$RUNNER" scripts/run_fair_vision_matrix.py --models "$key" \
    --execute --resume --output results/vision_server
  cleanup
  trap - EXIT
  if [[ "$MODE" == run && "${JEVLIGHT_RELEASE_COMPLETED_MODELS:-0}" == 1 ]]; then
    "$RUNNER" - "$key" <<'PY'
import sys
from scripts.vision_server_storage import release
release(sys.argv[1])
print('Released completed model weights and environment: ' + sys.argv[1], flush=True)
PY
    uv cache clean
  fi
done
echo "Finished. Results: $ROOT/results/vision_server"
