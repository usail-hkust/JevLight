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
| `valen` | Valen, Valen-Decision-1.5 |
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
| Valen 0.8B/2B, Valen-Decision-1.5 0.8B/2B | `valen` | `native` |
| Decider 4B, Valen 4B, Valen-Decision-1.5 4B, Lev, Kev 27B, Clef 27B, Open-Jev 2B/9B | `pooling-engine` | `step` |
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

## Valen-Decision-1.5

`valen-decision-1.5-0.8b`, `-2b` and `-4b` pin `Valen-Team/Valen-Decision-1.5-{0.8B,2B,4B}`
and select the `valen-decision-1.5` family in `serving.toml`. The family has its own runtime
classes, so the Valen 1.0 checkpoints keep their existing code path:

| Path | Valen 1.0 (`valen`) | Valen-Decision-1.5 (`valen-decision-1.5`) |
| --- | --- | --- |
| Author runtime | `ValenNative` | `ValenDecision15Native` |
| vLLM pooling runtime | `ValenPoolingNative` | `ValenDecision15PoolingNative` |
| Engine architecture | `ValenMarkerEngine` | `ValenDecision15MarkerEngine` |
| Engine config / worker | `ValenConfig`, `NativePoolingWorker` | `ValenDecision15Config`, `ValenDecision15PoolingWorker` |

Both generations publish `model_type = "valen_qwen"`; the 1.5 checkpoints add
`valen_decision_version = "1.5"`, `valen_full_attention_mask = "bbox_blocks"` and a
16384-token compiler limit (`valen_max_length`), which `max_length` follows. The block
mask applies to the full-attention layers: the state prefix is bidirectional and does
not attend to the question region, the chat-turn glue sees the prefix, and the decision
questions share one bidirectional block. The author runtime runs the checkpoint's own
`model.predict` / `forward_state_batch`. The vLLM engine reads the block boundaries
from the two closing chat turns of each prompt, checks them against the compiler's
segment ids before every request, and serves each prompt as one complete prefill
(chunked prefill disabled); the worker reports how many rows ran under the block mask.

### Image states and `bbox` questions

The benchmark sends text states with `choice` and `noul` questions, and the published
results use nothing else. The author runtime also accepts what Valen-Decision-1.5 adds
beyond that, so the same local service can be used for image experiments:

- a state of the form `{"messages": [...]}` passes to the checkpoint unchanged and may
  carry inline PNG or JPEG images as `image_url` data URLs; any other state is serialized
  to JSON text as before;
- a `bbox` question (`instructions`, and an optional `image` index when the state has
  several images) is answered by the checkpoint's grounding head with a normalized
  `bbox` `[x1, y1, x2, y2]`, its centre `point` and a `confidence`.

```bash
curl -s http://127.0.0.1:8123/v1/systemone -H 'Content-Type: application/json' -d '{
  "state": {"messages": [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo..."}},
    {"type": "text", "text": "A camera view of one junction."}]}]},
  "questions": {
    "queue": {"type": "bbox", "instructions": "the longest queue"},
    "phase": {"type": "choice", "instructions": "Choose the next phase.",
              "criteria": {"NTST": "north-south through", "ETWT": "east-west through"}}}}'
```

These requests run one at a time through the checkpoint's own `model.predict`, also when
they arrive in a batch. `bbox` answers are checked for four ordered edges, a point and a
confidence in `[0, 1]`; `choice` and `noul` answers in the same request keep the benchmark
checks. The vLLM pooling runtime is text-only and rejects image states and `bbox`
questions with an error, so use `inference_engine = "author"` (the bundled 0.8B and 2B
profiles; override it for 4B). `run_jevlight.py` does not send image states or `bbox`
questions.

### Recorded validation

One NVIDIA H200, 13 November 2026; `valen` environment with torch 2.8.0+cu128 and
transformers 5.4.0, `pooling-engine` environment with vLLM 0.19.0 and torch 2.10.0+cu128.
These are parity checks and single smoke episodes, not benchmark results: nothing here is
part of `assets/`.

**Benchmark prompts.** The 98 fixed and cooperative prompt cases, compared with the
checkpoint's own `model.predict` in float32. bfloat16 moves the checkpoint's own answers
by a few hundredths, so each row is read against that floor and against a control that
runs the checkpoint under a deliberately wrong causal mask. Probability differences:

| Size | Recording | Median | p90 | Max | Choices differing |
| --- | --- | ---: | ---: | ---: | ---: |
| 0.8B | checkpoint in bfloat16 (floor); author runtime, single requests | 0.0023 | 0.0201 | 0.0609 | 0 of 98 |
| 0.8B | author runtime, one batch of 98 | 0.0027 | 0.0198 | 0.0396 | 0 of 98 |
| 0.8B | vLLM pooling runtime | 0.0013 | 0.0111 | 0.0237 | 0 of 98 |
| 0.8B | causal-mask control | 0.1642 | 0.4301 | 0.6934 | 51 of 98 |
| 2B | checkpoint in bfloat16 (floor); author runtime, single requests | 0.0029 | 0.0095 | 0.0172 | 0 of 98 |
| 2B | author runtime, one batch of 98 | 0.0023 | 0.0086 | 0.0140 | 2 of 98 |
| 2B | vLLM pooling runtime | 0.0018 | 0.0081 | 0.0251 | 7 of 98 |
| 2B | causal-mask control | 0.1293 | 0.3670 | 0.5370 | 25 of 98 |
| 4B | checkpoint in bfloat16 (floor); author runtime, single requests | 0.0017 | 0.0079 | 0.0221 | 0 of 98 |
| 4B | author runtime, one batch of 98 | 0.0022 | 0.0080 | 0.0249 | 0 of 98 |
| 4B | vLLM pooling runtime | 0.0020 | 0.0051 | 0.0132 | 0 of 98 |
| 4B | causal-mask control | 0.0811 | 0.2571 | 0.4908 | 42 of 98 |

The author runtime answers single requests identically to the checkpoint. The seven 2B
choices that differ under the vLLM pooling runtime are one repeated phase question whose
two best phases are 0.04 apart in float32; the bundled 2B profile uses the author runtime.

**Image states and `bbox` questions.** Eight drawings per size, each with two `bbox`
questions, one `choice` and one `noul`, through `NativeBackend.evaluate` and
`evaluate_batch`: all 16 boxes and every probability were identical to the checkpoint's
own `predict`, with equal input-token counts, for 0.8B, 2B and 4B. A batch mixing an image
request with a text request returned both.

**End to end.** One complete `run_jevlight.py` episode per size with the bundled serving
profile and `jevlight_jinan-1_s1.json` (3600 simulated seconds), served through
`scripts.experiments.serve_decision_model`:

| Size | Engine | Model decisions | Failure fallbacks | Errors | AQL | AWT (s) | ATT (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.8B | author | 2859 | 0 | 0 | 511.95 | 292.89 | 545.51 |
| 2B | author | 2865 | 0 | 0 | 880.17 | 514.38 | 749.98 |
| 4B | vLLM pooling | 2867 | 0 | 0 | 115.42 | 66.15 | 326.55 |

The remaining 42 experiment configs per size were generated but not run.
