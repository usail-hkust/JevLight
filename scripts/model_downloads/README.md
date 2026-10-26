# Model preparation

Run from the repository root. The frozen `models.json` catalog records each model ID and revision. Model weights, shared backbones and author source repositories are stored under ignored `.local/`; integrity evidence and experiment outputs go under `results/`.

```bash
uv sync --locked --extra sumo --extra preparation
uv run python scripts/model_downloads/download.py --models laya gliner2.5-decide
uv run python scripts/model_downloads/fetch_sources.py
uv run python scripts/model_downloads/verify_snapshots.py --models laya gliner2.5-decide
```

Select model keys explicitly, or use `--models all` to select the complete catalog. Per-model entry points such as `scripts/model_downloads/kev-9b/download.py` use the same downloader. Frozen revisions, resumable transfers, LFS hashes and shared-base identities are retained.

## Isolated environments

| Environment | Model families |
| --- | --- |
| `encoder` | Laya, GLiNER2.5-Decide, Agent-Jev |
| `decoder` | Kev, Von, Decider, Clef, Bespoke-Nimble, Lev |
| `decision-heads` | d3-flash, d3, Perplexity Decider Flash v1.2 / 27B v1.2 |
| `valen` | Valen |
| `open-jev` | Open-Jev |
| `pooling-engine` | Optional pooling/marker engine adapters |
| `native-engine` | Dedicated vLLM author decision heads |
| `open-jev-fla` | Optional fused Open-Jev backend |

Install only the environments required for the selected models:

```bash
uv sync --locked --project scripts/model_downloads/environments/encoder
```

These environments preserve author dependency constraints. Optional vLLM and fused-kernel adapters require a separately compatible engine environment; the author environment alone does not install or validate those backends. The `native_flash_split` bridge requires its declared Torch/CUDA ABI. CUDA device selection is supplied through the deployment environment, and no device identifiers are bundled.

For download and CPU preparation only, without starting a model server or experiment:

```bash
uv sync --locked --project scripts/model_downloads/environments/decision-heads
uv run --locked python scripts/model_downloads/prepare.py \
  --models pplx-decider-flash-v1.2 d3-flash d3 pplx-decider-v1.2 \
  --author-environment scripts/model_downloads/environments/decision-heads \
  --workers 1 --range-workers 2
```

Each model is downloaded, verified against its complete frozen file list and shard
index, then audited through its native CPU encoder before the next model. Existing
files resume safely; a conflicting frozen identity is rejected. `--verify-existing`
skips transfers and requires complete snapshots. Reports distinguish CPU preparation
from outstanding GPU, engine and SUMO qualification. The four checkpoints publish
complete weights and readout heads under Apache-2.0; preserve their LICENSE and NOTICE.
The environment follows the authors' pinned packages, including Torch 2.14; check
driver/runtime compatibility separately before GPU use and do not modify system
drivers to satisfy an installation. CPU audit alone is not a GPU compatibility test.

Fetch the pinned `vllm-jev` source before installing `native-engine`. Export author-head
checkpoints with `python -m scripts.model_downloads.export_native_engine --model <key>`
in that environment. The merged Open-Jev export uses
`python -m scripts.model_downloads.export_open_jev_engine --model <key>`.

Configurations using `batch_fla_package_path` load isolated FLA packages after the
author runtime. Install only these packages into the configured directory:

```bash
uv pip install --target .local/environments/open-jev-fla/batch_packages --no-deps \
  flash-linear-attention==0.5.2 fla-core==0.5.2 einops==0.8.2
```

## Serving and validation

`config/<model>/serving.toml` specifies the checkpoint, complete-input context budget and optional backend settings. Start `python -m scripts.experiments.serve_decision_model` in the corresponding environment, with `--config` and a `--request-log` inside `results/`. `--batch-runtime native` installs the native capacity-adaptive batch adapter; `--attention` selects an explicit compatible attention implementation. For the dedicated vLLM author-head path, `--engine-selection` supplies a locally validated JSON profile with `checkpoint`, `capacity`, `native_modes`, and `progress_path`.

The serving profile and experiment configuration have separate roles:

- `serving.toml`: model weights, backend, context limits and service port.
- Experiment JSON: traffic scenario, ordinary/Co mode, service URL and batch request size.

`run_jevlight.py` connects to a running service; it does not load weights or start the
model server. Use the repository downloader to prepare complete snapshots and their
`manifest.json`, including shared backbones. An arbitrary downloaded checkpoint
folder alone is insufficient: adapters resolve pinned backbones from the manifests
and may import the pinned author sources. If storing snapshots elsewhere, preserve
the manifest layout and update `weights_path` and referenced backbone paths.

For the bundled serving profiles, select these environment/runtime combinations:

| Models | Environment | `--batch-runtime` |
| --- | --- | --- |
| Laya, Laya multilingual, Agent-Jev, GLiNER2.5-Decide | `encoder` | `native` |
| Kev 0.8B/4B/9B, Clef Flash, Decider 2B, Bespoke-Nimble 9B, Von | `decoder` | `native` |
| Valen 0.8B/2B | `valen` | `native` |
| Decider 4B, Valen 4B, Lev, Kev 27B, Clef 27B, Open-Jev 2B/9B | `pooling-engine` | `step` |
| Open-Jev 27B | `open-jev` | `step` |
| d3-flash, d3, Perplexity Decider Flash v1.2 / 27B v1.2 | `decision-heads` | `step` |

These four profiles retain the author reference backend. D3 batches independent
question rows in one author forward. Perplexity batches complete independent joint
requests; `batch_backend = "author_packed"` selects its optional packed implementation
after installing the environment's `acceleration` extra. Packed sequence boundaries
and GPU readout completion are checked explicitly. The author's D3 ROCm fast path
is platform specific. Evaluate current dedicated-head vLLM/SGLang support before
qualification; support for the backbone alone is insufficient. No alternative
engine or packed implementation is enabled by a CPU preparation report.

Optional fused dependencies and engine constraints above still apply. These are code
paths, not a claim that every backend has been qualified on every device.

For example, after preparing Laya, keep its service running in one terminal:

```bash
uv run --locked --project scripts/model_downloads/environments/encoder \
  python -m scripts.experiments.serve_decision_model \
  --config config/laya/serving.toml --request-log results/laya/requests.jsonl \
  --batch-runtime native
```

In another terminal, run the selected condition:

```bash
uv run --locked --extra sumo python run_jevlight.py \
  --config config/laya/jevlight_jinan-1_s1.json --jev_batch_size 196
```

Set `jev_base_url` in the experiment JSON to match the service host and port.
`jev_batch_size` may also be placed in the JSON. It defaults to zero when absent;
selecting a model JSON does not by itself enable batching. The value 196 requests
a complete step for the largest bundled network; the backend grades GPU chunk
capacity. `python -m scripts.experiments.step_batch_runner` invokes the same runner
with extended batch error diagnostics and is used by the experiment queue.

Generate full local/cooperative prompt fixtures with:

```bash
uv run python -m scripts.experiments.preparation_cases
uv run python -m scripts.experiments.cooperative_cases
```

Validate native encoding and candidate lengths without truncation, independent question/answer mapping, actual GPU execution, memory margin, throughput, and both modes in SUMO. Full-step batching is requested before capacity reduction. Record chunk sizes and reasons for reduction in `results/`. A backend is not qualified by HTTP concurrency, memory allocation or CPU/mock tests. Probability comparisons are not an acceptance gate; retain valid candidate phases and finite traffic metrics. Use three warmup and ten measured iterations for initial screening.

The common experiment matrix and result definitions are documented in [experiment settings](../../docs/experiment_settings.md). Models, adapters and shared backbones are retained after runs.

## Experiment entry point

Inspect the 42 conditions without loading a model:

```bash
uv run python -m scripts.experiments.model_experiments --model laya --stage matrix
```

In the selected model environment, `--stage qualify` runs the existing complete-input,
GPU batch and paired SUMO checks; `--stage formal` runs or resumes the matrix.
These stages are explicit operations and are not part of repository cleanup or unit tests.
Use the same serving options as above. `--author-environment` selects the CPU encoding
environment when it differs from the default author environment.

`--scope` accepts a local JSON list of model keys assigned to a deployment; without it,
all 21 checkpoints must be qualified before formal runs. A formal run requires current
ordinary and cooperative evidence for every model in that scope. Device assignment
uses `CUDA_VISIBLE_DEVICES`; independent services can use separate ports and output
files. The stop marker `results/experiments/stop` prevents the next condition from
starting. Results retain individual attempts, original summaries and decision traces;
`matrix_summary.json` contains three-seed means, sample standard deviations and paired
Co-minus-local differences after all 42 conditions complete.

## StartLux-Decision on 4A800

The StartLux v1.1 Instant checkpoints (`0.8B/2B/4B/9B/27B`) use a compatibility
overlay instead of a second venv: keep the shared `a800-vllm` interpreter and put
`.local/environments/startlux-vllm/overlay` first on `PYTHONPATH`. The overlay holds
vLLM 0.19.1, transformers 5.8.1 and `startlux-decide` 1.1.0; the base environment
stays at vLLM 0.19.0 for the existing queues. `StartLuxNative` adds the overlay to
both child processes (`vllm serve` and `startlux-decide serve`).

Download pinned snapshots into `.local/models/startlux-<size>/weights` and write the
per-folder `manifest.json` used by `acceptance_identity`:

```bash
HF_ENDPOINT=https://hf-mirror.com \
  uv run --project .local/environments/a800-vllm/.venv \
  python -m scripts.model_downloads.startlux_ranges \
  --connections 16 startlux-4b startlux-9b startlux-27b
```

The scripts default to the domestic `https://hf-mirror.com` endpoint and set
`HF_HUB_DISABLE_XET=1`: the mirror's Xet reconstruction path returns 401, while the
non-Xet CDN works. Large shards use 16 ranged connections; `startlux_snapshots.py`
is the resumable hub fallback and handles the small metadata files. Both write the
same manifest (revision, per-file size and SHA-256). Never commit weights.

The experiment queue is not tied to a machine or a model. Each node runs one
`global_queue` process and every GPU pulls conditions from the same pending pool in
the shared home:

```bash
uv run python -m scripts.experiments.global_queue run --node a800 --supervise
uv run python -m scripts.experiments.global_queue plan
```

`config/decision_models/global_queue.json` pins both nodes' GPU ids, step ports,
per-GPU idle instances, service environments and the model order with per-model
batch caps. Each worker is wrapped in `gpu_idle_ctl.sh run`, so the occupancy
daemon releases the GPU before the backend loads and resumes afterwards.
`results/experiments/queue_status*.json` feed the dashboard; per-condition records
and native request logs stay under `results/experiments/`. Pause, resume,
interrupt and graceful stop are control files shared by both nodes — see
`scripts/experiments/global_queue.py` and `docs/experiment_settings.md`.
