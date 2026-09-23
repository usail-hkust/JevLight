# JevLight

Traffic signal control with **Jev**, the System One decision model — applied to
SUMO simulation on top of the observation and control-flow conventions of
[ChatLight](https://github.com/SQLai2099/ChatLight)'s migrated
**LLMLight / CoLLMLight** paths.

Jev is not a chat model: one request sends a **state** plus a map of typed
**questions**, and returns one typed answer per question, evaluated in
parallel. JevLight maps signal control directly onto that interface — the
model picks an action from the options you give it, with pure-text prompts and
millisecond-scale decisions.

## How signal control maps onto Jev

| Traffic control concept | Jev API concept |
| --- | --- |
| One intersection's snapshot (queue, approaching vehicles by segment, waiting times) | `state` (JSON) |
| "Which phase next?" — ETWT / NTST / ELWL / NLSL | one `choice` question, criteria = the phases |
| "Is this junction congested?" (logged for analysis) | one speculative `noul` question in the same request |
| Chosen phase + full distribution + confidence | `answers.<id>.choice` / `.probabilities` / `.confidence` |

**Network packaging** (default): every active intersection is packed into one
shared state with one question each — the whole road network decides in a
**single API call per control step** (Jev evaluates all questions against the
state in parallel, so extra questions barely change latency). With
`--packaging per_intersection` each junction gets its own request, matching
LLMLight's request pattern.

Fallbacks follow the ChatLight source conventions:

- Empty junctions (no vehicles) never call the API; they use the exact
  CoLLMLight local waiting-time ranking.
- Failed / rate-limited / unparsable requests keep the previous signal
  (`--fallback previous`, default) or use the local ranking
  (`--fallback ranking`).
- Answers with `confidence < --min_confidence` are rejected the same way.

## Repository layout

```
run_jevlight.py            # experiment entry point (mirrors run_LLMLight.py)
jevlight/
  controller.py            # JevLightController, state + question construction
  jev_client.py            # Jev API client: community MCP or official TypeSafe
  observation.py           # SUMO snapshot -> observations (LLMLight semantics)
  env_bridge.py            # minimal SUMOEnv setup (ChatLight InteractionEnv core)
  config.py                # env config + dataset registry
  evaluation_metrics.py    # canonical metrics (from ChatLight)
  rolling_evaluation.py    # hourly/final rolling recorder (from ChatLight)
  wandb_utils.py           # optional W&B logging
utils/
  sumo_env.py              # SUMO runtime (from ChatLight, profiling hook stubbed)
  phase_utils.py           # phase helpers (from ChatLight)
data/Jinan/3_4/            # one SUMO scenario (12 intersections)
tests/                     # unit tests (no network, no SUMO)
```

## Setup

Requirements: Python 3.10+, [SUMO](https://sumo.dlr.de) ≥ 1.20 with `traci` /
`sumolib` on `PYTHONPATH` or installed via pip (`eclipse-sumo`), plus the
Python dependencies:

```bash
pip install -r requirements.txt
export SUMO_HOME=/path/to/sumo   # if traci/sumolib are not pip-installed
```

## API keys

Two transports are supported:

| Transport | Endpoint | Key |
| --- | --- | --- |
| `mcp` (default) | Jev community server `https://www.jevai.org/api/mcp`, tool `jev_decide` | `$JEV_API_KEY` (`jev_...`) |
| `official` | TypeSafe `POST https://api.typesafe.ai/v1/systemone` | `$TYPESAFE_API_KEY` |

Both transports answer the same `state` + typed `questions` request.

Community-endpoint notes (observed behavior):

- Do not pass `--jev_model` with official aliases such as `jev-latest`; the
  endpoint expects identifiers like `typesafe-ai/jev`. By default the model
  field is omitted so the server chooses.
- The free endpoint enforces a burst quota and returns transient upstream
  failures under load. The client retries those with exponential backoff and
  paces requests (`--jev_min_interval`, default 3s for `mcp`); steps that
  still fail fall back per `--fallback`, and each decision trace records
  whether it was a real Jev answer or a fallback.

Both answer the same `state` + typed `questions` request.

## Usage

```bash
# 1) Pipeline smoke test, no API key (deterministic mock decisions):
python run_jevlight.py --mock_jev --count 60

# 2) Community MCP endpoint (network packaging, one request per step):
export JEV_API_KEY=jev_...
python run_jevlight.py --dataset jinan --count 900

# 3) Official TypeSafe API, confidence-gated fallback to local ranking:
export TYPESAFE_API_KEY=...
python run_jevlight.py --jev_transport official --count 900 \
    --min_confidence 0.5 --fallback ranking

# 4) LLMLight-style per-intersection requests + rolling evaluation:
python run_jevlight.py --packaging per_intersection --count 3600 --rolling_evaluation
```

Each run writes `records/JevLight/<run_id>/`:

- `jev_decisions.jsonl` — one trace per decision: question, answer,
  probabilities, confidence, latency, token usage, fallback reason
- `summary.json` — final metrics + aggregate Jev usage stats
- plus SUMO's own logs via `batch_log()`

## Datasets

The Jinan 3×4 scenario ships with the repo. To use Hangzhou / NewYork / MZW,
copy the corresponding folders from ChatLight's `data/` (see
`jevlight/config.py` for the expected paths).

## Tests

```bash
python -m pytest tests/ -q
```

## Provenance

The observation semantics (`collect_observations`), the local phase ranking
(`rank_phases`), the SUMO runtime, the metrics, and the runner's control loop
come from ChatLight's migrated LLMLight / CoLLMLight inference paths; Jev
replaces the text-completion LLM as the decision model.
