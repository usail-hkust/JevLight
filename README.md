# JevLight

Traffic signal control with **Jev**, the System One decision model — applied to SUMO simulation on top of the observation and control-flow conventions of **LLMLight / CoLLMLight**.

Jev is not a chat model: one request sends a **state** plus a map of typed **questions**, and returns one typed answer per question, evaluated in parallel. JevLight maps signal control directly onto that interface — the model picks an action from the options you give it, with pure-text prompts and millisecond-scale decisions.

## How signal control maps onto Jev

| Traffic control concept | Jev API concept |
| --- | --- |
| One intersection's snapshot (queue, approaching vehicles by segment, waiting times) | `state` (JSON) |
| "Which phase next?" — ETWT / NTST / ELWL / NLSL | one `choice` question, criteria = the phases |
| "Is this junction congested?" (logged for analysis) | one speculative `noul` question in the same request |
| Chosen phase + full distribution + confidence | `answers.<id>.choice` / `.probabilities` / `.confidence` |

**Network packaging** (default): every active intersection is packed into one shared state with one question each — the whole road network decides in a **single API call per control step** (Jev evaluates all questions against the state in parallel, so extra questions barely change latency). With `--packaging per_intersection` each junction gets its own request, matching LLMLight's request pattern.

Fallbacks follow the ChatLight source conventions:

- Empty junctions (no vehicles) never call the API; they use the exact CoLLMLight local waiting-time ranking.
- Failed / rate-limited / unparsable requests keep the previous signal (`--fallback previous`, default) or use the local ranking (`--fallback ranking`).
- Answers with `confidence < --min_confidence` are rejected the same way.

## Repository layout

```
run_jevlight.py            # experiment entry point (mirrors run_LLMLight.py)
jevlight/
  controller.py            # JevLightController, state + question construction
  jev_client.py            # Jev API client: MCP, official TypeSafe, or local
  local_server.py          # local /v1/systemone service (vLLM logit readout, mock)
  observation.py           # SUMO snapshot -> observations (LLMLight semantics)
  env_bridge.py            # minimal SUMOEnv setup (ChatLight InteractionEnv core)
  config.py                # env config + dataset registry
  evaluation_metrics.py    # canonical metrics (from ChatLight)
  rolling_evaluation.py    # hourly/final rolling recorder (from ChatLight)
  wandb_utils.py           # optional W&B logging
scripts/serve_jev.sh       # start a local Jev-style model service (vLLM/mock)
scripts/serve_3d.py        # 3D SUMO visualizer bridge (traci -> SSE)
jevlight/viz_server.py     # visualizer server core (standalone + --visualize)
viz/                       # three.js frontend for the 3D visualizer
utils/
  sumo_env.py              # SUMO runtime (from ChatLight, profiling hook stubbed)
  phase_utils.py           # phase helpers (from ChatLight)
data/Jinan/3_4/            # one SUMO scenario (12 intersections)
tests/                     # unit tests (no network, no SUMO)
```

## Setup

Requirements: Python 3.10+, [SUMO](https://sumo.dlr.de) ≥ 1.20 with `traci` / `sumolib` on `PYTHONPATH` or installed via pip (`eclipse-sumo`), plus the Python dependencies:

```bash
pip install -r requirements.txt
export SUMO_HOME=/path/to/sumo   # if traci/sumolib are not pip-installed
```

## API keys

Three transports are supported:

| Transport | Endpoint | Key |
| --- | --- | --- |
| `mcp` (default) | Jev community server `https://www.jevai.org/api/mcp`, tool `jev_decide` | `$JEV_API_KEY` (`jev_...`) |
| `official` | TypeSafe `POST https://api.typesafe.ai/v1/systemone` | `$TYPESAFE_API_KEY` |
| `local` | self-hosted Jev-compatible server (`$JEV_LOCAL_BASE_URL`, default `http://127.0.0.1:8123`) | none |

All transports answer the same `state` + typed `questions` request.

Community-endpoint notes (observed behavior):

- Do not pass `--jev_model` with official aliases such as `jev-latest`; the endpoint expects identifiers like `typesafe-ai/jev`. By default the model field is omitted so the server chooses.
- The free endpoint enforces a burst quota and returns transient upstream failures under load. The client retries those with exponential backoff and paces requests (`--jev_min_interval`, default 3s for `mcp`); steps that still fail fall back per `--fallback`, and each decision trace records whether it was a real Jev answer or a fallback.

## Open-source Jev-style models (local transport)

Jev itself is closed, but the open System One ecosystem (Laya, Tev1, Von, Jebadiah, …) converges on Jev's wire format: a local server exposing `POST /v1/systemone`. The `local` transport talks to any of them — no API key, no request pacing.

This repo ships a serving stack of its own, `scripts/serve_jev.sh`:

```bash
# 1) GPU-free pipeline smoke test: /v1/systemone with deterministic
#    max-pressure answers (same semantics as --mock_jev):
scripts/serve_jev.sh --backend mock

# 2) Open checkpoint on vLLM (the "Jev-vLLM" route), e.g. Tev1:
scripts/serve_jev.sh --model tev1                    # alias -> HF repo id
scripts/serve_jev.sh --model <org>/<checkpoint>      # any HF causal LM
#    or point the adapter at an already-running OpenAI-compatible endpoint:
python -m jevlight.local_server --backend vllm \
    --vllm_base_url http://gpu-host:8000/v1 --vllm_model <name>
```

The vLLM route deploys two layers: vLLM serves the checkpoint on an OpenAI-compatible endpoint, and `jevlight.local_server` adapts it to `/v1/systemone` — each question becomes one letter-labelled prompt and the option probabilities are read from next-token logprobs in a single prefill (no decoding, millisecond-scale decisions). Then run JevLight against it:

```bash
python run_jevlight.py --jev_transport local --dataset jinan --count 900
```

Any *other* Jev-compatible server works too — start it on port 8123 (or set `--jev_base_url` / `$JEV_LOCAL_BASE_URL`) and the `local` transport talks to it directly.

Caveats, stated plainly: logit-readout probabilities from a general open checkpoint are **uncalibrated** — they are model scores, not Jev's calibrated confidence. Compare models on `jev_decisions.jsonl` traces and canonical metrics, and keep `--fallback` enabled.

## Agent modes

`--agent` selects the prompt wording and request pattern on the same Jev interface — the two migrated ChatLight baselines with Jev as the decision model:

| Mode | Prompt | Packaging | Congestion Noul |
| --- | --- | --- | --- |
| `jevlight` | JevLight: one agent per intersection, local view only (LLMLight pattern) | per_intersection | no |
| `cojevlight` (default) | CoJevLight: one network-level agent, coordinated view (CoLLMLight pattern) | network | yes |

```bash
python run_jevlight.py --agent jevlight   # per-intersection agent
python run_jevlight.py --agent cojevlight # network-level agent (default)
```

The pre-release names `llmlight` / `collmlight` remain accepted as aliases. `--packaging` and `--no_speculative` still override the per-mode defaults; each decision trace records the active `agent_mode`.

## 3D visualization (SUMO)

`scripts/serve_3d.py` runs (or attaches to) a SUMO simulation and streams it to a city-scale 3D viewer (three.js, no build step): asphalt lanes with sidewalks, dashed lane markings, stop lines and zebra crossings, procedural street buildings with sun and soft shadows, vehicle models by SUMO vehicle class (car / bus / truck / two-wheeler, colored per vehicle), traffic-light heads, and play/pause/step/speed controls:

```bash
python scripts/serve_3d.py                    # Jinan at 1x, open http://127.0.0.1:8300
python scripts/serve_3d.py --speed 4          # 4x playback
python scripts/serve_3d.py --attach 127.0.0.1:8813   # watch an already-running SUMO
python scripts/serve_3d.py --sumo_args "--seed 3"    # extra SUMO flags
```

**Traffic-camera mode**: click `📹 Cam` (or 🎲) to install a virtual surveillance camera at a random junction, or click any junction in the camera list to switch. The page then shows a 2×2 grid of live views — one per approach direction (北/东/南/西 labeled) — rendered from pole-mounted cameras at that intersection, with a pole marker visible in the main 3D view.

Architecture: one thread owns the traci connection (vehicle subscriptions + TLS states per step) and publishes snapshots; browsers get the network once via `GET /api/network` and per-step frames over SSE (`GET /api/stream`); `POST /api/command` drives play/pause/step/speed. traci positions are shifted into net coordinates so vehicles and lane geometry share one frame. On an HPC login node, port-forward with `ssh -L 8300:127.0.0.1:8300`; the page needs internet access once to load three.js from the CDN (or vendor `three.module.js` into `viz/js/` and drop the import map).

### Visualizing a JevLight experiment

`run_jevlight.py --visualize` attaches the same viewer to the run's own simulation — no separate SUMO, one frame per control step of the actual experiment, and the page's play/pause/step buttons gate the experiment loop itself:

```bash
python run_jevlight.py --mock_jev --count 60 --visualize          # opens the browser
python run_jevlight.py --jev_transport local --visualize --viz_hold
```

Options: `--viz_host`/`--viz_port` (next free port is picked automatically), `--viz_hold` keeps serving the final 3D state after the run until Ctrl-C. On a headless node the browser cannot open itself — the runner prints the URL plus the matching `ssh -L` forwarding command.

## Usage

```bash
# 1) MaxPressure baseline, no decision model at all (dry run):
python run_jevlight.py --dry_run --count 3600

# 2) Pipeline smoke test, no API key (deterministic mock decisions):
python run_jevlight.py --mock_jev --count 60

# 3) Community MCP endpoint (network packaging, one request per step):
export JEV_API_KEY=jev_...
python run_jevlight.py --dataset jinan --count 900

# 4) Official TypeSafe API, confidence-gated fallback to local ranking:
export TYPESAFE_API_KEY=...
python run_jevlight.py --jev_transport official --count 900 \
    --min_confidence 0.5 --fallback ranking

# 5) Open Jev-style model served locally (see the local-transport section):
scripts/serve_jev.sh --model tev1          # start the service first
python run_jevlight.py --jev_transport local --count 900

# 6) Per-intersection (jevlight agent) requests + rolling evaluation:
python run_jevlight.py --agent jevlight --count 3600 --rolling_evaluation
```

`--dry_run` swaps the controller for a classic **MaxPressure** agent: each intersection activates the phase whose lanes hold the most vehicles (queued + approaching — the same pressure the mock Jev scores), entirely local, zero Jev requests, no key or transport needed. Traces record the per-phase pressures, and `summary.json` carries `"dry_run": true` with zero Jev usage — the canonical no-LLM baseline to compare the Jev paths against.

Each run writes `records/JevLight/<run_id>/`:

- `jev_decisions.jsonl` — one trace per decision: question, answer, probabilities, confidence, latency, token usage, fallback reason
- `summary.json` — final metrics + aggregate Jev usage stats
- plus SUMO's own logs via `batch_log()`

## Datasets

Four SUMO scenarios ship with the repo (selected with `--dataset`, traffic file with `--traffic_file`; see `jevlight/config.py` for the registry):

| Dataset key | Network | Intersections | Traffic files |
| --- | --- | --- | --- |
| `jinan` | 3×4 | 12 | real, real_2000, real_2500, synthetic_24h_6000 |
| `hangzhou` | 4×4 | 16 | real, real_5816, synthetic_24000_60min |
| `newyork` | 28×7 | 196 | real_double, real_triple |
| `newyork_16x3` | 16×3 | 48 | real |

MZW and Manhattan are not included; copy them from the upstream project's `data/` and register them in `jevlight/config.py` if needed. `results/benchmark_jinan.json` keeps the baseline benchmark numbers produced by the previous CityFlow-based version of this repository.

## Tests

```bash
python -m pytest tests/ -q
```

## Provenance

The observation semantics (`collect_observations`), the local phase ranking (`rank_phases`), the SUMO runtime, the metrics, and the runner's control loop come from ChatLight's migrated LLMLight / CoLLMLight inference paths; Jev replaces the text-completion LLM as the decision model.
