"""Run JevLight signal control on the SUMO stack.

Control flow mirrors ChatLight's ``run_LLMLight.py``: collect observations,
decide one action per intersection, step SUMO, log traces and metrics.  The
decision model is Jev — either the community MCP endpoint (default,
``$JEV_API_KEY``) or the official TypeSafe API (``$TYPESAFE_API_KEY``).
See ``jevlight/controller.py`` for the question design.

Examples:
    # Mock transport, no API key needed (pipeline smoke test):
    python run_jevlight.py --mock_jev --count 60

    # Community MCP endpoint (default transport):
    export JEV_API_KEY=jev_...
    python run_jevlight.py --dataset jinan --count 900

    # Official TypeSafe API:
    export TYPESAFE_API_KEY=...
    python run_jevlight.py --jev_transport official --dataset jinan --count 900
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from tqdm import tqdm

from jevlight.config import (
    DATASETS,
    DIC_PATH,
    EIGHT_PHASE_LIST,
    EIGHT_PHASE_PHASES,
    dic_traffic_env_conf,
    setup_dataset_config,
)
from jevlight.controller import (
    JEV_FALLBACKS,
    JEV_PACKAGINGS,
    JevLightController,
)
from jevlight.env_bridge import JevLightEnv
from jevlight.evaluation_metrics import calculate_evaluation_metrics_from_env
from jevlight.jev_client import (
    DEFAULT_JEV_MODEL,
    DEFAULT_MCP_BASE_URL,
    DEFAULT_OFFICIAL_BASE_URL,
    JEV_TRANSPORTS,
    JevClient,
    resolve_jev_api_key,
)
from jevlight.observation import collect_observations
from jevlight.rolling_evaluation import RollingMetricRecorder
from jevlight.wandb_utils import safe_wandb_finish, safe_wandb_log, wandb_init_if_enabled


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run JevLight signal control with a Jev decision model"
    )
    parser.add_argument(
        "--jev_transport",
        choices=JEV_TRANSPORTS,
        default="mcp",
        help=(
            "mcp: community server at www.jevai.org/api/mcp (default, uses "
            "$JEV_API_KEY); official: TypeSafe System One API (uses "
            "$TYPESAFE_API_KEY)"
        ),
    )
    parser.add_argument(
        "--jev_model",
        default=DEFAULT_JEV_MODEL,
        help=(
            "Model ID passed through to the endpoint; official default is "
            f"{DEFAULT_JEV_MODEL}. Pass an empty string to let the server "
            "choose (recommended for the community endpoint)"
        ),
    )
    parser.add_argument(
        "--jev_api_key",
        default=None,
        help="Jev API key; defaults to $JEV_API_KEY / $TYPESAFE_API_KEY",
    )
    parser.add_argument(
        "--jev_base_url",
        default=None,
        help=(
            "Override the endpoint URL (defaults: "
            f"{DEFAULT_MCP_BASE_URL} for mcp, "
            f"{DEFAULT_OFFICIAL_BASE_URL} for official)"
        ),
    )
    parser.add_argument(
        "--jev_timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--jev_retries",
        type=int,
        default=3,
        help="Retry attempts on rate-limit/network errors (default: 3)",
    )
    parser.add_argument(
        "--packaging",
        choices=JEV_PACKAGINGS,
        default="network",
        help=(
            "network: one request per step with every active intersection as a "
            "parallel question (default); per_intersection: one request per "
            "active intersection per step, like LLMLight"
        ),
    )
    parser.add_argument(
        "--fallback",
        choices=JEV_FALLBACKS,
        default="previous",
        help=(
            "Signal used when an answer is missing, invalid, rate-limited, or "
            "below --min_confidence: previous = keep the previous signal "
            "(source convention, default); ranking = local waiting-time ranking"
        ),
    )
    parser.add_argument(
        "--min_confidence",
        type=float,
        default=0.0,
        help=(
            "Reject Jev answers whose confidence is below this value and use "
            "the fallback signal (default: 0.0 = disabled)"
        ),
    )
    parser.add_argument(
        "--no_speculative",
        action="store_true",
        help="Drop the congestion Noul question from each request",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=8,
        help="Concurrent requests for per_intersection packaging",
    )
    parser.add_argument(
        "--mock_jev",
        action="store_true",
        help="Deterministic local answers for pipeline smoke tests (no API)",
    )
    parser.add_argument("--memo", default="JevLight")
    parser.add_argument("--proj_name", default="JevLight")
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
    parser.add_argument("--eightphase", action="store_true")
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
    return parser.parse_args()


def build_configs(args, dataset_config, run_id):
    num_intersections = args.num_intersections or dataset_config["num_intersections"]
    phase = dic_traffic_env_conf["PHASE"]
    phase_list = dic_traffic_env_conf["PHASE_LIST"]
    if args.eightphase:
        phase = EIGHT_PHASE_PHASES
        phase_list = EIGHT_PHASE_LIST

    agent_config = {
        "POLICY": "jevlight",
        "LLM_MODEL": args.jev_model,
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
        "MODEL_NAME": "jevlight",
        "MODEL": "jevlight",
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
    paths.update({
        "PATH_TO_MODEL": os.path.join("model", args.memo, run_id),
        "PATH_TO_WORK_DIRECTORY": os.path.join("records", args.memo, run_id),
        "PATH_TO_DATA": os.path.join(
            "data", dataset_config["template"], str(dataset_config["road_net"])
        ),
        "PATH_TO_ERROR": os.path.join("errors", args.memo),
    })
    return agent_config, env_config, paths


def calculate_metrics(env, total_reward, namespace="final"):
    """Same metric names and aggregate definitions as ChatLight's runner."""
    metrics = calculate_evaluation_metrics_from_env(env, namespace)
    metrics[f"{namespace}/reward"] = float(total_reward)
    return metrics


def build_wandb_group(dataset_config, env_config, traffic_file):
    traffic_file_str = traffic_file.split(".")[0]
    phase_count = len(env_config.get("PHASE", {}))
    roadnet_group = f"{dataset_config['template']}-{dataset_config['road_net']}"
    return f"JevLight-{roadnet_group}-{traffic_file_str}-{phase_count}_Phases"


def run(args):
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

    api_key = resolve_jev_api_key(args.jev_api_key)
    if not args.mock_jev and api_key is None:
        raise ValueError(
            "Jev API key missing: pass --jev_api_key or set "
            "$JEV_API_KEY / $TYPESAFE_API_KEY (or use --mock_jev)"
        )

    timestamp = time.strftime("%m_%d_%H_%M_%S")
    run_id = f"jevlight_{Path(args.traffic_file).stem}_{timestamp}_pid{os.getpid()}"
    agent_config, env_config, paths = build_configs(args, dataset_config, run_id)

    client = JevClient(
        transport=args.jev_transport,
        model=args.jev_model or None,
        api_key=api_key,
        base_url=args.jev_base_url,
        timeout=args.jev_timeout,
        max_retries=args.jev_retries,
        mock=args.mock_jev,
    )
    controller = JevLightController(
        client,
        args.duration,
        packaging=args.packaging,
        fallback=args.fallback,
        min_confidence=args.min_confidence,
        speculative=not args.no_speculative,
        max_workers=args.max_workers,
    )

    simulator = JevLightEnv(
        agent_config,
        env_config,
        paths,
        args.traffic_file,
    )
    env = simulator.env
    if args.start_time:
        simulator.reset_env_with_start_time(args.start_time)

    logger = wandb_init_if_enabled(
        env_config,
        project=args.proj_name,
        entity=args.wandb_entity,
        group=build_wandb_group(dataset_config, env_config, args.traffic_file),
        name=run_id,
        config={**vars(args), "run_id": run_id},
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
    trace_path = Path(paths["PATH_TO_WORK_DIRECTORY"]) / "jev_decisions.jsonl"
    rolling_recorder = None
    if args.rolling_evaluation:
        rolling_recorder = RollingMetricRecorder(
            args.evaluation_output_dir or paths["PATH_TO_WORK_DIRECTORY"],
            total_duration=args.count,
            hourly_interval=args.hourly_interval,
            logger=logger,
            metadata={
                "method": "jevlight",
                "jev_transport": args.jev_transport,
                "jev_model": args.jev_model,
                "packaging": args.packaging,
                "fallback": args.fallback,
                "min_confidence": args.min_confidence,
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
            desc="jevlight simulation",
            unit="s",
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
                    f"[SUMO-TIME] controller=jevlight "
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
    summary_path = Path(paths["PATH_TO_WORK_DIRECTORY"]) / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "jev_transport": args.jev_transport,
                "jev_model": args.jev_model,
                "packaging": args.packaging,
                "fallback": args.fallback,
                "min_confidence": args.min_confidence,
                **metrics,
                "jev": controller.usage_summary(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    env.batch_log()
    env.end_engine()
    print(json.dumps(metrics, indent=2))
    print(f"Decision log: {trace_path}")
    print(f"Summary: {summary_path}")
    return metrics


if __name__ == "__main__":
    run(parse_args())
