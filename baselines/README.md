# Baselines on the JevLight evaluation stack

This folder implements the standard traffic-signal baseline methods so they run through JevLight's own simulation loop and metric computation — the same `SUMOEnv`, the same `collect_observations`, the same `jevlight/evaluation_metrics.py` — making every number directly comparable with Jev/CoJev runs. `run_jevlight.py` is not modified: baselines have their own entry point here.

**Included baselines:** LLMLight and CoLLMLight (LLM, inference-time control), CoLight, PressLight, MPLight, AttendLight, AdvancedDQN (TensorFlow RL), CityLight (PyTorch MAPPO), MaxPressure (strict lane-pressure formula), Webster (refined Webster cycle-time method), and FixedTime (uniform 15 s splits).

## Usage

Run a baseline through the shared evaluation flow (results land in `results/<baseline>/<memo>/<run_id>/` with the same `summary.json` / `jev_decisions.jsonl` layout as a JevLight run):

```bash
# Heuristic baselines (only needs SUMO):
python -m baselines.run_baseline --baseline fixedtime --count 3600
python -m baselines.run_baseline --baseline maxpressure --count 3600
python -m baselines.run_baseline --baseline webster --count 3600

# LLM baselines against a served checkpoint; --mock_llm answers locally:
python -m baselines.run_baseline --baseline llmlight --mock_llm --count 60
python -m baselines.run_baseline --baseline collmlight --mock_llm --count 60

# RL baselines: train first, then evaluate the checkpoint here:
python -m baselines.rl.train --model Colight --dataset jinan --count 3600 --num_rounds 50
python -m baselines.run_baseline --baseline colight --rl_checkpoint model/Colight/<traffic>_<ts> --count 3600
```

Shared arguments mirror `run_jevlight.py` (`--dataset`, `--traffic_file`, `--duration`, `--count`, `--seed`, `--eightphase`, `--rolling_evaluation`, ...); baseline-specific knobs are listed in `python -m baselines.run_baseline --help`. Experiment configs live in `baselines/config/<baseline>/<experiment>.json` (not the project's `config/` directory, so the model-experiment queue never picks them up). The runner supports neither `--visualize` nor checkpoint resume — those remain `run_jevlight.py` features.

RL training checkpoints land in `model/<memo>/<traffic>_<timestamp>/round_<N>_inter_0.h5` (`.pt` for CityLight) with `agent.conf` written next to them at the end of training; evaluation defaults to the highest round present (`--rl_round` overrides) and reads that `agent.conf` automatically. Dependencies: the heuristic baselines need nothing beyond the core project, the generic LLM path needs `openai` (`baselines-llm` extra), the five TensorFlow models need `tensorflow-cpu` (`baselines-rl` extra), and CityLight needs `torch` (`baselines-rl-torch` extra).

## LLM endpoint configuration

LLMLight talks to a served fine-tuned checkpoint as raw text completions (`--llmlight_base_url`, default `http://localhost:8001/v1`; optionally `--llmlight_tokenizer_path` for the dynamic request budget; key from `$LLMLIGHT_LLM_API_KEY` / `$LOCAL_LLM_API_KEY`). CoLLMLight talks to any OpenAI-compatible chat endpoint (`$COLLMLIGHT_TOKENIZER_JSON` plus `$COLLMLIGHT_MAX_CONTEXT_TOKENS` enable its budget; endpoint from `$LOCAL_LLM_BASE_URL`, default `http://localhost:8000/v1`). The generic fallback (any other model id, e.g. `siliconflow/...` or `deepseek/...`) uses the corresponding API keys, or an explicit `--llm_base_url` / `--llm_api_key` for any other OpenAI-compatible server. The generic client's context policy can be tuned with `$BASELINE_LLM_TOKENIZER_PATH` (counting tokenizer), `$BASELINE_LLM_MAX_CONTEXT_TOKENS`, `$BASELINE_LLM_GEN_TOKEN_CAP` and `$BASELINE_LLM_SINGLE_MESSAGE_TOKEN_CAP`.

## Implementation notes

These notes spell out the semantics each baseline uses on JevLight's stack.

- **Observation layer.** The LLMLight/CoLLMLight controllers consume `jevlight.observation`: movement occupancy divides by `(road_length // 9) * num_physical_lanes`, `avg_wait` aggregates across all physical lanes of a movement, and the observation carries the full lane-relation topology.
- **MaxPressure.** The score is Σ(upstream queue − downstream queue) per phase, with the downstream aggregate per destination movement (via `IntersectionObservation.lane_relations`) and movements exiting the network contributing nothing. When the road topology is unavailable the score degrades to upstream-only; every trace records the per-movement values and `topology_available`. Note the name collision: `run_jevlight.py --dry_run` also groups under `results/maxpressure/` with a different formula (own-lane queued + approaching) — keep the memos distinct.
- **Webster.** The `Webster` class implements the refined Webster cycle-time method; the controller wrapper builds lane conditions from observations, recomputes the plan every update window (60 s) and follows it in whole decision intervals. Demand is estimated as the observed vehicle stock per movement over the update window.
- **FixedTime.** Uniform 15 s per phase in cycle order; `--fixed_time_splits` generalizes the splits.
- **RL evaluation reward.** Evaluation uses JevLight's fixed `DIC_REWARD_INFO {"queue_length": -0.25}`, so `final/reward` is uniformly comparable across all baselines and JevLight runs. All other metrics (travel time, waiting time, queue length, vehicle counts) are reward-independent.
- **RL training.** Training always runs in-process; `--use_wandb` defaults to false. Checkpoints carry the agent config, and evaluation reads it back automatically, forcing `EPSILON` to zero for deterministic rollouts.
- **LLM client.** The generic backend supports the OpenAI-compatible paths only (no in-process vLLM loading — serve the model behind an endpoint instead); the counting tokenizer loads from an explicit `tokenizer.json` (no `transformers` dependency), and the client accepts explicit `base_url`/`api_key` overrides. `--llmlight_tokenizer_path` defaults to unset, meaning the static `--max_tokens` budget.

## Layout

`run_baseline.py` is the evaluation entry (a faithful mirror of `run_jevlight.py`'s loop; `tests/test_baselines_runner.py` guards the configuration parity against `run_jevlight.build_configs`). `maxpressure.py`, `fixedtime.py`, `webster.py` are the heuristic controllers. `llmlight/` holds the LLMLight/CoLLMLight controller, prompts, and generic LLM client. `rl/` holds the training pipeline (`train.py`, `pipeline/` with the Generator/ConstructSample/Updater/model_test stages and the agent implementations), the configuration registry (`rl_config.py`), and the evaluation controller (`eval_controller.py`). Tests live in the project's `tests/` directory (`test_baseline_*.py`, `test_baselines_runner.py`).
