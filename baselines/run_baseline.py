"""Run baseline controllers on the JevLight evaluation stack.

The control loop, environment, observations, and metrics are JevLight's own —
this entry reuses them unchanged (``jevlight.env_bridge.JevLightEnv``,
``jevlight.observation.collect_observations``,
``jevlight.evaluation_metrics``, ``jevlight.rolling_evaluation``) and mirrors
``run_jevlight.py``'s loop line for line so baseline results are directly
comparable with Jev/CoJev runs.  ``run_jevlight.py`` itself is never touched.

Baselines: LLMLight, CoLLMLight (LLM), CoLight, PressLight, MPLight,
AttendLight, AdvancedDQN, CityLight (RL, train with
``python -m baselines.rl.train``), MaxPressure (strict lane pressure),
Webster, FixedTime.

Examples:
    # Heuristic baselines, purely local decisions:
    python -m baselines.run_baseline --baseline fixedtime --count 3600
    python -m baselines.run_baseline --baseline maxpressure --count 3600
    python -m baselines.run_baseline --baseline webster --count 3600

    # LLM baselines against a served checkpoint (mock needs no server):
    python -m baselines.run_baseline --baseline llmlight --mock_llm --count 60
    python -m baselines.run_baseline --baseline collmlight --mock_llm --count 60

    # RL baseline: train first, then evaluate the checkpoint here:
    python -m baselines.rl.train --model Colight --count 3600 --num_rounds 50
    python -m baselines.run_baseline --baseline colight \
        --rl_checkpoint model/Colight/<memo>/<traffic>_<ts> --count 3600

Unsupported versus run_jevlight.py: --visualize, --checkpoint_every_steps and
--resume_from (the loop keeps no checkpoint machinery).
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Dict

from tqdm import tqdm

from baselines import BASELINES, LLM_BASELINES, RL_BASELINES, RL_MODEL_NAMES, build_controller
from jevlight.config import (
    DATASETS,
    DIC_PATH,
    EIGHT_PHASE_LIST,
    EIGHT_PHASE_PHASES,
    dic_traffic_env_conf,
    setup_dataset_config,
)
from jevlight.env_bridge import JevLightEnv
from jevlight.evaluation_metrics import calculate_evaluation_metrics_from_env
from jevlight.observation import collect_observations
from jevlight.rolling_evaluation import RollingMetricRecorder
from jevlight.simulation_checkpoint import OutputLease
from jevlight.wandb_utils import safe_wandb_finish, safe_wandb_log, wandb_init_if_enabled


def parse_bool(value):
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise argparse.ArgumentTypeError("expected true or false")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Run a baseline on the JevLight simulation and "
            "metric stack (results land in results/<baseline>/<memo>/<run_id>)"
        )
    )
    parser.add_argument(
        "--baseline",
        choices=BASELINES,
        default=None,
        help="Baseline controller to run; results are grouped under results/<baseline>/",
    )
    parser.add_argument(
        "--config",
        help="JSON experiment parameters in baselines/config/<baseline>/<experiment>.json",
    )
    parser.add_argument(
        "--print_config",
        action="store_true",
        help="Print resolved parameters without running an experiment",
    )
    # Shared dataset/env arguments: same names and defaults as run_jevlight.py.
    parser.add_argument("--memo", default="Baselines")
    parser.add_argument("--proj_name", default="JevLight-Baselines")
    parser.add_argument(
        "--dataset",
        default="jinan",
        help=f"Dataset key; registered: {', '.join(sorted(DATASETS))}",
    )
    parser.add_argument("--traffic_file", default="anon_3_4_jinan_real.rou.xml")
    parser.add_argument("--road_net", default=None)
    parser.add_argument("--roadnet_file", default=None)
    parser.add_argument("--num_intersections", type=int, default=None)
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--count", type=int, default=3600)
    parser.add_argument("--start_time", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--eightphase", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--use_wandb",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--wandb_entity", default=None)
    parser.add_argument(
        "--rolling_evaluation",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Emit canonical hourly_results/* curves and one complete final/* result",
    )
    parser.add_argument("--hourly_interval", type=int, default=3600)
    parser.add_argument("--evaluation_output_dir", default=None)
    # LLM baselines (LLMLight / CoLLMLight), mirroring run_LLMLight.py.
    parser.add_argument(
        "--backbone",
        default=None,
        help="CoLLMLight backbone model id (default: the ported DEFAULT_BACKBONE)",
    )
    parser.add_argument(
        "--llmlight_provider",
        choices=("local", "siliconflow"),
        default="local",
        help="LLMLight inference backend: served local checkpoint or SiliconFlow API",
    )
    parser.add_argument(
        "--llmlight_model",
        default=None,
        help="LLMLight model id (default: the ported DEFAULT_LLMLIGHT_MODEL)",
    )
    parser.add_argument(
        "--llmlight_base_url",
        default=None,
        help=(
            "OpenAI-compatible base URL of the served LLMLight checkpoint "
            "(local provider only; default http://localhost:8001/v1)"
        ),
    )
    parser.add_argument(
        "--llmlight_tokenizer_path",
        default=None,
        help=(
            "Optional tokenizer.json path (file or directory) for the served "
            "LLMLight checkpoint's dynamic request budget; unset uses the "
            "static --max_tokens budget"
        ),
    )
    parser.add_argument("--llmlight_max_context_tokens", type=int, default=4096)
    parser.add_argument(
        "--max_tokens",
        type=int,
        default=None,
        help="Generation cap (default: 1024 for llmlight, 8192 for collmlight)",
    )
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument(
        "--top_p",
        type=float,
        default=None,
        help="Nucleus sampling (default: 1.0 for llmlight, 0.95 for collmlight)",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=8,
        help="Concurrent LLM requests",
    )
    parser.add_argument(
        "--mock_llm",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Deterministic local answers for pipeline smoke tests (no server)",
    )
    parser.add_argument(
        "--llm_base_url",
        default=None,
        help="Override for the generic OpenAI-compatible LLM backend's base URL",
    )
    parser.add_argument(
        "--llm_api_key",
        default=None,
        help="Override for the generic LLM backend's API key (never stored in configs)",
    )
    # CoLLMLight.
    parser.add_argument("--history_window", type=int, default=5)
    parser.add_argument(
        "--communication_threshold",
        type=float,
        default=0.0,
        help="Probability threshold for including learned neighbor-lane traffic",
    )
    parser.add_argument(
        "--disable_psr",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Disable CoLLMLight spatiotemporal reasoning (ATR)",
    )
    # FixedTime.
    parser.add_argument(
        "--fixed_time_splits",
        default="15,15,15,15",
        help=(
            "Comma-separated green seconds per phase in cycle order "
            "(default 15,15,15,15, the uniform plan); length must "
            "match the phase count"
        ),
    )
    # Webster.
    parser.add_argument("--webster_update_frequency", type=int, default=60)
    parser.add_argument("--webster_min_green", type=float, default=8.0)
    parser.add_argument("--webster_min_cycle", type=float, default=32.0)
    parser.add_argument("--webster_max_cycle", type=float, default=120.0)
    parser.add_argument("--webster_saturation_flow", type=float, default=0.38)
    parser.add_argument("--webster_vehicle_length", type=float, default=8.0)
    # RL evaluation.
    parser.add_argument(
        "--rl_checkpoint",
        default=None,
        help="Checkpoint directory produced by baselines.rl.train (contains round_*_inter_0.*)",
    )
    parser.add_argument(
        "--rl_round",
        type=int,
        default=None,
        help="Training round to evaluate (default: the highest round present)",
    )
    parser.add_argument(
        "--rl_agent_conf",
        default=None,
        help="Optional agent.conf JSON from the training run to override agent hyperparameters",
    )
    parser.add_argument(
        "--rl_device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="Device for the CityLight baseline (TF models follow their own placement)",
    )

    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--baseline")
    config_parser.add_argument("--config")
    known, _ = config_parser.parse_known_args(argv)
    config_path = known.config
    if config_path:
        try:
            defaults = load_experiment_defaults(parser, config_path)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        parser.set_defaults(**defaults)
    args = parser.parse_args(argv)
    if not args.baseline:
        parser.error("--baseline is required (or provide --config baselines/config/<baseline>/<experiment>.json)")
    if config_path and Path(config_path).resolve().parent.name != args.baseline:
        parser.error(
            "Experiment configs must be baselines/config/<baseline>/<experiment>.json "
            f"matching the selected baseline (got {args.baseline}, config {config_path})"
        )
    if args.baseline == "citylight" and args.eightphase:
        parser.error("citylight supports exactly four actions; --eightphase is not supported")
    if not 0 <= args.communication_threshold <= 1:
        parser.error("communication_threshold must be between 0 and 1")
    if args.webster_update_frequency <= 0:
        parser.error("webster_update_frequency must be positive")
    if args.webster_min_green < 0:
        parser.error("webster_min_green must be nonnegative")
    if args.webster_min_cycle > args.webster_max_cycle:
        parser.error("webster_min_cycle must not exceed webster_max_cycle")
    if args.webster_saturation_flow <= 0 or args.webster_vehicle_length <= 0:
        parser.error("webster_saturation_flow and webster_vehicle_length must be positive")
    if args.rl_round is not None and args.rl_round < 0:
        parser.error("rl_round must be nonnegative")
    return args


def load_experiment_defaults(parser, filename):
    """Validate file defaults; explicit CLI flags retain argparse precedence.

    Mirrors run_jevlight.load_experiment_defaults with the baselines' own
    config root; keys must be existing CLI arguments and secrets stay out.
    """
    path = Path(filename).resolve()
    config_root = Path(__file__).resolve().parent / "config"
    if path.parent.parent != config_root or path.suffix != ".json":
        raise ValueError("Baseline configs must be baselines/config/<baseline>/<experiment>.json")
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {filename}: {exc}") from exc
    if not isinstance(values, dict):
        raise ValueError("Experiment config must be a JSON object")
    actions = {a.dest: a for a in parser._actions}
    forbidden = {"help", "config", "print_config", "llm_api_key"}
    for key, value in values.items():
        if key not in actions or key in forbidden:
            raise ValueError(f"Unknown or prohibited config parameter: {key}")
        action = actions[key]
        if value is None and action.default is None:
            continue
        if action.type is parse_bool or isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse.BooleanOptionalAction)):
            valid = type(value) is bool
        elif action.type is int:
            valid = type(value) is int
        elif action.type is float:
            valid = type(value) in (int, float)
        else:
            valid = isinstance(value, str)
        if not valid:
            raise ValueError(f"Invalid type for config parameter {key}: {value!r}")
        if action.choices is not None and value not in action.choices:
            raise ValueError(f"Invalid value for config parameter {key}: {value!r}")
    return values


def experiment_parameters(args):
    """Reproducible resolved parameters without credentials or preflight flags."""
    return {key: value for key, value in vars(args).items()
            if key not in {"llm_api_key", "print_config"}}


def build_configs(args, dataset_config, run_id):
    """Mirror of run_jevlight.build_configs (run_jevlight.py:378-438).

    Three controlled differences: ``POLICY``/``MODEL_NAME``/``MODEL`` carry the
    baseline name, and the results group is the baseline name (or the config
    parent directory).  Everything else is kept identical so a baseline run
    and a JevLight run share the exact same env configuration;
    tests/test_baselines_runner.py guards the parity.
    """
    num_intersections = args.num_intersections or dataset_config["num_intersections"]
    phase = dic_traffic_env_conf["PHASE"]
    phase_list = dic_traffic_env_conf["PHASE_LIST"]
    if args.eightphase:
        phase = EIGHT_PHASE_PHASES
        phase_list = EIGHT_PHASE_LIST

    agent_config = {
        "POLICY": args.baseline,
        "LLM_MODEL": (
            args.backbone or args.llmlight_model
            if args.baseline in LLM_BASELINES
            else None
        ),
        "CONTROL_INTERVAL": args.duration,
    }
    env_config = copy.deepcopy(dic_traffic_env_conf)
    env_config.update({
        "NUM_AGENTS": num_intersections,
        "NUM_INTERSECTIONS": num_intersections,
        "RUN_COUNTS": args.count,
        "MIN_ACTION_TIME": args.duration,
        "MEASURE_TIME": args.duration,
        "GREEN_TIME": args.duration - 5,
        "YELLOW_TIME": 5,
        "MODEL_NAME": args.baseline,
        "MODEL": args.baseline,
        "PROJECT_NAME": args.proj_name,
        "USE_WANDB": args.use_wandb,
        "TRAFFIC_FILE": args.traffic_file,
        "ROADNET_FILE": dataset_config["roadnet_file"],
        "LIST_STATE_FEATURE": [
            "cur_phase_four",
            "lane_num_waiting_vehicle_in",
            "adjacency_matrix",
        ],
        "DIC_REWARD_INFO": {"queue_length": -0.25},
        "SEED": getattr(args, "seed", 1),
        "PHASE": phase,
        "PHASE_LIST": phase_list,
    })
    paths = copy.deepcopy(DIC_PATH)
    model_name = (
        Path(args.config).parent.name
        if getattr(args, "config", None)
        else args.baseline
    )
    model_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in model_name)
    if model_name in {"", ".", ".."}:
        raise ValueError("model name must identify a results subdirectory")
    memo = args.memo
    if Path(memo).name != memo or memo in {"", ".", ".."}:
        raise ValueError("memo must be a single directory name")
    result_dir = os.path.join("results", model_name, memo, run_id)
    if args.evaluation_output_dir:
        output = Path(args.evaluation_output_dir).resolve()
        if not output.is_relative_to(Path("results").resolve()):
            raise ValueError("evaluation_output_dir must be inside results/")
    paths.update({
        "PATH_TO_MODEL": os.path.join(result_dir, "model"),
        "PATH_TO_WORK_DIRECTORY": result_dir,
        "PATH_TO_DATA": os.path.join(
            "data", dataset_config["template"], str(dataset_config["road_net"])
        ),
        "PATH_TO_ERROR": os.path.join(result_dir, "errors"),
    })
    return agent_config, env_config, paths


def calculate_metrics(env, total_reward, namespace="final"):
    """Same metric names and aggregate definitions as the JevLight runner."""
    metrics = calculate_evaluation_metrics_from_env(env, namespace)
    metrics[f"{namespace}/reward"] = float(total_reward)
    return metrics


def build_wandb_group(baseline, dataset_config, env_config, traffic_file):
    """run_jevlight.build_wandb_group with the baseline name as the label."""
    traffic_file_str = traffic_file.split(".")[0]
    phase_count = len(env_config.get("PHASE", {}))
    roadnet_group = f"{dataset_config['template']}-{dataset_config['road_net']}"
    return f"{baseline}-{roadnet_group}-{traffic_file_str}-{phase_count}_Phases"


def baseline_details(args) -> Dict[str, Any]:
    """Baseline-specific summary block appended to summary.json."""
    if args.baseline == "fixedtime":
        return {"fixed_time_splits": args.fixed_time_splits}
    if args.baseline == "webster":
        return {
            "webster": {
                "update_frequency": args.webster_update_frequency,
                "min_green_time": args.webster_min_green,
                "min_cycle_time": args.webster_min_cycle,
                "max_cycle_time": args.webster_max_cycle,
                "saturation_flow": args.webster_saturation_flow,
                "vehicle_length": args.webster_vehicle_length,
            }
        }
    if args.baseline in RL_BASELINES:
        return {
            "rl": {
                "model": RL_MODEL_NAMES[args.baseline],
                "checkpoint": args.rl_checkpoint,
                "round": args.rl_round,
            }
        }
    return {}


def run(args):
    # Release SUMO and output ownership on every exit, including interrupts.
    with ExitStack() as resources:
        return _run(args, resources)


def _run(args, resources):
    if args.duration <= 5:
        raise ValueError("duration must be greater than the 5-second yellow time")
    if args.count <= 0:
        raise ValueError("count must be positive")

    dataset_config = setup_dataset_config(args.dataset)
    if args.road_net:
        dataset_config["road_net"] = args.road_net
    if args.roadnet_file:
        dataset_config["roadnet_file"] = args.roadnet_file
    traffic_path = os.path.join(
        "data", dataset_config["template"], str(dataset_config["road_net"]), args.traffic_file
    )
    roadnet_path = os.path.join(
        "data", dataset_config["template"], str(dataset_config["road_net"]), dataset_config["roadnet_file"]
    )
    if not os.path.isfile(traffic_path):
        raise FileNotFoundError(f"Traffic file does not exist: {traffic_path}")
    if not os.path.isfile(roadnet_path):
        raise FileNotFoundError(f"Roadnet file does not exist: {roadnet_path}")

    timestamp = time.strftime("%m_%d_%H_%M_%S")
    run_id = f"{args.baseline}_{Path(args.traffic_file).stem}_{timestamp}_pid{os.getpid()}"
    agent_config, env_config, paths = build_configs(args, dataset_config, run_id)
    run_directory = Path(paths["PATH_TO_WORK_DIRECTORY"]).resolve()
    if not run_directory.is_relative_to(Path("results").resolve()):
        raise ValueError("Run directory must be inside results/")
    lease = resources.enter_context(OutputLease(run_directory))
    if args.evaluation_output_dir and Path(args.evaluation_output_dir).resolve() != run_directory:
        resources.enter_context(OutputLease(args.evaluation_output_dir))
    if (run_directory / "summary.json").exists():
        raise ValueError("Run already has a summary; preserve it and verify completion before resuming")

    controller = build_controller(args.baseline, args, env_config)
    packaging = "per_intersection" if args.baseline in LLM_BASELINES else "none"

    simulator = JevLightEnv(agent_config, env_config, paths, args.traffic_file)
    env = simulator.env
    resources.callback(env.close)
    (Path(paths["PATH_TO_WORK_DIRECTORY"]) / "experiment_config.json").write_text(
        json.dumps(experiment_parameters(args), indent=2), encoding="utf-8"
    )
    if args.start_time:
        simulator.reset_env_with_start_time(args.start_time)
    # RL controllers read canonical env state features at decision time.
    if hasattr(controller, "bind_env"):
        controller.bind_env(env)

    logger = wandb_init_if_enabled(
        env_config,
        project=args.proj_name,
        entity=args.wandb_entity,
        group=build_wandb_group(args.baseline, dataset_config, env_config, args.traffic_file),
        name=run_id,
        config={**experiment_parameters(args), "run_id": run_id},
    )
    if logger is not None:
        logger.define_metric("final/checkpoint")
        for metric_name in (
            "final/reward",
            "final/avg_travel_time",
            "final/avg_waiting_time",
            "final/avg_queue_len",
            "final/queuing_vehicle_num",
            "final/vehicle_count",
            "final/arrived_vehicle_count",
            "final/observed_vehicle_count",
            "final/intersection_observation_count",
            "final/queue_observation_step_count",
        ):
            logger.define_metric(metric_name, step_metric="final/checkpoint")
    trace_path = run_directory / "jev_decisions.jsonl"
    rolling_recorder = None
    if args.rolling_evaluation:
        rolling_recorder = RollingMetricRecorder(
            args.evaluation_output_dir or run_directory,
            total_duration=args.count,
            hourly_interval=args.hourly_interval,
            logger=logger,
            metadata={
                "method": args.baseline,
                "agent_mode": args.baseline,
                "jev_transport": None,
                "jev_model": agent_config.get("LLM_MODEL"),
                "packaging": packaging,
                "fallback": None,
                "min_confidence": 0.0,
                "traffic_file": args.traffic_file,
            },
        )
        rolling_recorder.attach(env, evaluation_start_time=args.start_time)
    total_reward = 0.0
    current_time = float(env.get_current_time())
    evaluation_start_time = current_time
    simulation_end_time = args.start_time + args.count
    if args.rolling_evaluation:
        remaining_duration = max(0, simulation_end_time - int(current_time))
        max_steps = (remaining_duration + args.duration - 1) // args.duration
    else:
        max_steps = args.count // args.duration
    step = 0
    done = False
    with trace_path.open("a", encoding="utf-8") as trace_file:
        with tqdm(
            total=max_steps * args.duration,
            desc=f"{args.baseline} simulation",
            unit="s",
            initial=step * args.duration,
        ) as progress:
            while not done and step < max_steps:
                observations = collect_observations(env)
                actions, traces = controller.decide(observations, step)
                step_duration = args.duration
                if args.rolling_evaluation:
                    step_duration = min(
                        args.duration,
                        max(1, int(simulation_end_time - current_time)),
                    )
                _, rewards, done, _ = env.step(actions, min_action_time=step_duration)
                total_reward += float(sum(rewards))
                for trace in traces:
                    trace_file.write(json.dumps(trace, ensure_ascii=False) + "\n")
                trace_file.flush()
                current_time = float(env.get_current_time())
                step += 1
                progress.update(step_duration)
                simulated_elapsed = current_time - evaluation_start_time
                usage = controller.usage_summary()
                print(
                    f"[SUMO-TIME] controller={args.baseline} "
                    f"step={step}/{max_steps} current={current_time:.0f}s "
                    f"elapsed={simulated_elapsed:.0f}/{max_steps * args.duration}s "
                    f"requests={usage['requests']} "
                    f"failures={usage['failures']} "
                    f"rate_limited={usage['rate_limited']} "
                    f"latency_mean_s={usage['latency_mean_s'] or 0:.3f}",
                    flush=True,
                )

    if rolling_recorder is not None:
        metrics = rolling_recorder.finalize(env)
    else:
        checkpoint_start = int(round(evaluation_start_time))
        checkpoint_end = int(round(current_time))
        metrics = calculate_metrics(env, total_reward, namespace="final")
        metrics.update({
            "final/checkpoint": 0,
            "final/start_time": checkpoint_start,
            "final/end_time": checkpoint_end,
            "final/duration": checkpoint_end - checkpoint_start,
        })
        safe_wandb_log(logger, metrics)
    safe_wandb_finish(logger)
    summary_path = run_directory / "summary.json"
    summary = {
        "run_id": run_id,
        "agent_mode": args.baseline,
        "baseline": args.baseline,
        "jev_transport": None,
        "jev_model": agent_config.get("LLM_MODEL"),
        "packaging": packaging,
        "fallback": None,
        "min_confidence": 0.0,
        "dry_run": False,
        "visualize": False,
        **metrics,
        "jev": controller.usage_summary(),
    }
    summary.update(baseline_details(args))
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    env.batch_log()
    env.end_engine()
    print(json.dumps(metrics, indent=2))
    print(f"Decision log: {trace_path}")
    print(f"Summary: {summary_path}")
    return metrics


if __name__ == "__main__":
    args = parse_args()
    if args.print_config:
        print(json.dumps(experiment_parameters(args), indent=2))
    else:
        run(args)
