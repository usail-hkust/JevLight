# Vision JevLight

The optional Vision path estimates traffic from camera images and then selects a
signal phase. Official Jev and three pinned open models use the same visual
agent, renderer, questions, control loop and metrics.

## Inputs and method

`--image_agent vlalight --image_renderer vlalight` enables two stages:

1. Perception: four separate approach images, labelled by vehicle travel direction,
   answer 24 choice questions about demand, queues and changes for the eight
   controlled movements. After the first step, the preceding step's four images
   are included too, for at most eight images per request.
2. Decision: the model chooses one of four phases using its visual estimates,
   the controller's previous signal and elapsed control information.

SUMO vehicle positions are used to render the scene. Simulator queue counts,
waiting times, occupancies and dynamic neighbour measurements are not supplied
to the model. The implementation borrows VLALight's renderer and two-stage
perception/decision idea; it does not reproduce the paper's six-frame video or
fast/slow inference switching.

The shared matrix disables visual cooperation. The optional
`--visual_cooperation` path routes camera-derived estimates using static lane
connections; it does not read neighbours' queues from SUMO. The experimental
`vlalight-grouped` agent uses lane masks calibrated only for Jinan 3_4 and is not
part of the shared four-model matrix. The older `--image_agent direct` path
instead asks a phase question against one composite camera image.

## Supported models

| Matrix key | Runtime | Version |
| --- | --- | --- |
| `jev-vision` | TypeSafe official multipart image API | `jev-1.14.0` |
| `wemm-jev` | `Rover00/WeMM-JEV`, author `D3Engine` | `a463f840c9259ff9139ab02181e01f20aca91b4b` |
| `d3-turbo` | `vllm-sr/d3-turbo`, author `system_one` | `a0f3e9e59ebd1202fe1d4de1c4c0f9a986758cbb` |
| `amos-1-large` | `mukaddamzaid/amos-1-large`, author engine | `d67e051c763dc88a1e3662a5003c1e1ea5ffaa74` |

Revisions and request limits live in [`config/vision_models.json`](../config/vision_models.json).
Local image references become ordered `Image 1`, `Image 2`, etc., preserving
direction and time associations. Author runtimes use their native decision heads
and BF16 weights, without quantization or CPU offload.

The upstream text Jev configurations remain unchanged at `jev-1.13.0`; the
visual matrix explicitly selects `jev-1.14.0` for image inference. Comparing
these two methods therefore also includes a model-version difference.

## Environment

The automated setup targets Ubuntu 24.04 / Linux x86_64. It needs Python 3, Git,
access to GitHub, Hugging Face and Python package repositories, and these system
packages (install uv as described in the main README; root/sudo is needed for
missing system packages):

```bash
sudo apt-get update
sudo apt-get install -y python3-venv xvfb xauth libgl1 libegl1 libopengl0 libglib2.0-0
```

Scripts create isolated Python 3.12 environments using uv under `.local/`.
The simulation environment uses the repository's `uv.lock` via
`uv sync --locked --extra sumo`, matching the baseline (currently SUMO and
traci/sumolib 1.28.0). Renderer dependencies are installed with constraints
exported from that lockfile, so they cannot replace its pinned core packages.
Setup fetches
the VLALight renderer and scene assets at revision
`9844f1b6bbd6b4fe80b481d3dd16fadce13c3b5d`, checking Git blob hashes.
GitHub CLI and old upload archives are not required.

Open-model launchers require one NVIDIA GPU with at least **70 GiB free VRAM**
before loading and at least 128 GB system RAM. This is a startup guard, not a
measured peak-memory guarantee. Select one GPU on a multi-GPU host using
`CUDA_VISIBLE_DEVICES`; the adapter does not implement tensor parallelism.
WeMM installs and checks a CUDA convolution wheel for Python 3.12,
torch 2.8.0/cu128 and CXX11 ABI. Validate the complete path on the actual GPU and
driver before scheduling formal runs.

Each checkpoint is approximately 49–52 GiB, plus dependencies and results.
An uncached model requires at least **105 GiB free disk** before preparation;
a cached model requires 40 GiB free. Keeping all three checkpoints requires more
space: 500 GB or more of working storage is a practical starting point when also
retaining experiment frames. All camera images are saved; monitor disk usage.
These checks do not reserve space for an entire campaign.

## Open models

From the repository root:

```bash
export CUDA_VISIBLE_DEVICES=0
# Install the simulation environment and fetch the pinned renderer.
bash scripts/setup_vision_runner.sh
# Prepare a model without starting experiments:
bash scripts/run_vision_server.sh --mode setup --models wemm-jev
# Run one model: seven flows, three seeds, 21 formal conditions.
bash scripts/run_vision_server.sh --models wemm-jev
# Run all three models serially: 63 formal conditions.
bash scripts/run_vision_server.sh --models wemm-jev d3-turbo amos-1-large
```

The launcher installs model dependencies in isolated environments, downloads
pinned weights, starts the loopback service and runs the shared matrix with
`--execute --resume`. It checks the eight-image/24-question interface before
simulation. It does not run an extra 30-second simulation. `HF_TOKEN` can be
supplied through the environment for Hub authentication. Models and results are
retained by default. With limited storage, opt into releasing completed models:

```bash
JEVLIGHT_RELEASE_COMPLETED_MODELS=1 bash scripts/run_vision_server.sh \
  --models wemm-jev d3-turbo amos-1-large
```

After all 21 conditions of a model pass validation, this option removes that
model's managed weights and isolated environment and cleans the project uv cache
before preparing the next model. Results and camera images are retained. A
failure stops the queue and preserves the failed model.

Use `bash scripts/run_vision_server.sh --help` for the launcher options.
The service binds to `127.0.0.1:8123`. Do not run multiple model services on that
port or start two preparation jobs in the same checkout. Use your scheduler or
terminal session manager for long-running jobs.

## Official Jev API

Official inference needs no local model GPU or open-model weights, but simulation
and rendering still need the graphics environment above. Configure a TypeSafe
key with official image access using environment variables, not configuration files:

```bash
bash scripts/setup_vision_runner.sh
read -rsp 'TypeSafe API key: ' TYPESAFE_API_KEY; echo
export TYPESAFE_API_KEY
unset JEV_API_KEY
.local/vision-runner/bin/python scripts/run_fair_vision_matrix.py \
  --models jev-vision --output results/vision_official
# Full official matrix: 21 conditions.
xvfb-run -a .local/vision-runner/bin/python scripts/run_fair_vision_matrix.py \
  --models jev-vision --execute --resume --output results/vision_official
```

Only `--execute` starts inference. Planning does not call the API, download
weights or run SUMO. Add `--flows jinan-1 --seeds 1 --limit 1` to restrict
execution to one condition. A full official
matrix requires approximately 662,400 logical evaluations, excluding preflight
and HTTP retries; this is not a price estimate.

## Shared experiment protocol and results

The matrix covers Jinan real/2000/2500, Hangzhou real/5816 and New York
double/triple, each with seeds 1/2/3. Formal simulations start at 0 and run for
3600 seconds, with **15-second control intervals**, 5 seconds of yellow on a
phase change and four phases. Smoke runs use the same settings with a 30-second
horizon when explicitly requested with `--smoke`; this is optional. Baseline
environment settings, networks, routes and canonical metrics
are shared; only the model method/input changes. Any failed or fallback image
decision invalidates the condition.

`scripts/run_fair_vision_matrix.py` creates the full 84-condition plan (official
plus three open models). Without `--execute` it only plans. Its `--models`,
`--flows`, `--seeds` and `--limit` arguments restrict execution; `--endpoint
MODEL=URL` selects an existing compatible local service. The bootstrap scripts
manage model preparation and service lifetime for the common workflow.

| Output | Location |
| --- | --- |
| Open-model plans, completion records, attempt logs and scores | `results/vision_server/{smoke,formal}/` |
| Official plans, completion records, attempt logs and scores | `results/vision_official/{smoke,formal}/` |
| Per-run configuration, summary, decision trace and frames | `results/jev-api/` |
| Open-model service logs | `logs/vision_server/<model>.log` |
| Installed model package versions | `results/vision_server/environment-<model>.txt` |

`scores.json` records completed seeds and their metric means/sample standard
deviations; individual completion records preserve raw values. To inspect a
current run, read its `formal/attempts/<id>/runner.log`. For example,
`elapsed=900/3600s` means that condition has simulated 25% of its horizon.

The entry scripts enable `--resume`: unchanged, hash-verified completed
conditions are skipped. Interrupted conditions restart at simulation time 0 in
a new attempt. Frozen plans bind code, configs and traffic hashes; do not edit
them to reuse a different implementation's results. Completion records contain
absolute artifact paths, so copying only `completed/` to another machine does
not provide portable resume. Preserve original results for separate aggregation.

Tests cover protocol, baseline configuration equality, adapters and resume
integrity without paid requests. GPU execution, dependencies and performance
remain unverified until exercised on the target system. Local author runtimes currently
use batch size 1 and serialized inference; a CUDA kernel microbenchmark does not
establish an end-to-end speedup.
