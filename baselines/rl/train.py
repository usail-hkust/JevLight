"""Train an RL traffic-signal baseline on the JevLight SUMO stack.

Trains CoLight, PressLight, MPLight, AttendLight, AdvancedDQN (TensorFlow) and
CityLight (PyTorch MAPPO) with the standard rollout → replay-sample →
network-update → per-round-test pipeline.  Checkpoints land in
``model/<memo>/<traffic>_<timestamp>/round_<N>_inter_0.h5`` (TF) or ``.pt``
(CityLight); evaluate one with ``python -m baselines.run_baseline --baseline
<name> --rl_checkpoint <dir>``.

Implementation notes: training always runs in-process (no multi-process
wrapper); ``--use_wandb`` defaults to false; heuristic methods are not part
of this entry (run them through ``baselines.run_baseline``); dataset
validation always checks the files on disk.

Examples:
    python -m baselines.rl.train --model Colight --dataset jinan --count 3600
    python -m baselines.rl.train --model CityLight --traffic_file anon_3_4_jinan_real_2000.rou.xml
"""

from __future__ import annotations

import argparse
import os
import time

from baselines.rl.pipeline.pipeline import Pipeline, merge
from baselines.rl.rl_config import (
    DIC_BASE_AGENT_CONF,
    LIST_SINGLE_MODEL,
    RL_BASE_ENV_CONF,
    get_model_config,
    split_simulation_timeline,
)
from jevlight.config import DIC_PATH, setup_dataset_config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Train an RL baseline (evaluation happens via baselines.run_baseline)"
    )
    parser.add_argument(
        "--model",
        required=True,
        choices=("Colight", "PressLight", "MPLight", "Attend", "AdvancedDQN", "CityLight"),
        help="RL method to train",
    )
    parser.add_argument(
        "--memo",
        default=None,
        help="Checkpoint directory label (default: the model name, so checkpoints land in model/<model>/<traffic>_<ts>)",
    )
    parser.add_argument("--proj_name", default="JevLight-Baselines")
    parser.add_argument("--dataset", default="jinan")
    parser.add_argument("--traffic_file", default="anon_3_4_jinan_real.rou.xml")
    parser.add_argument("--road_net", default=None)
    parser.add_argument("--roadnet_file", default=None)
    parser.add_argument("--num_intersections", type=int, default=None)
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--count", type=int, default=3600)
    parser.add_argument("--num_rounds", type=int, default=50)
    parser.add_argument("--gen", type=int, default=1, help="Rollout generators per round")
    parser.add_argument("--eightphase", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--use_wandb",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Track training with W&B (source default was true)",
    )
    parser.add_argument("--wandb_entity", default=None)
    return parser.parse_args(argv)


def main(in_args=None):
    args = in_args or parse_args()
    if args.model == "CityLight" and args.eightphase:
        raise ValueError("citylight supports exactly four actions; --eightphase is not supported")
    if args.duration <= 5:
        raise ValueError("duration must be greater than the 5-second yellow time")
    if args.num_rounds <= 0:
        raise ValueError("num_rounds must be positive")
    if args.gen <= 0:
        raise ValueError("gen must be positive")

    dataset_config = setup_dataset_config(args.dataset)
    if args.road_net:
        dataset_config["road_net"] = args.road_net
    if args.roadnet_file:
        dataset_config["roadnet_file"] = args.roadnet_file
    count = args.count
    template = dataset_config["template"]
    road_net = dataset_config["road_net"]
    roadnet_file = dataset_config["roadnet_file"]
    num_intersections = (
        args.num_intersections
        if args.num_intersections is not None
        else dataset_config["num_intersections"]
    )

    traffic_path = os.path.join("data", template, str(road_net), args.traffic_file)
    roadnet_path = os.path.join("data", template, str(road_net), roadnet_file)
    if not os.path.isfile(traffic_path):
        raise FileNotFoundError(f"Traffic file does not exist: {traffic_path}")
    if not os.path.isfile(roadnet_path):
        raise FileNotFoundError(f"Roadnet file does not exist: {roadnet_path}")
    if "24h" in args.traffic_file:
        count = 86400
    elif "7d" in args.traffic_file:
        count = 86400 * 7
    timeline = split_simulation_timeline(count)
    print(f"Running {args.model} on {args.traffic_file}")

    # Get model-specific configurations
    model_config = get_model_config(args.model)

    # Set up agent config
    dic_agent_conf_extra = dict(model_config["agent_config"])
    if args.eightphase and "FIXED_TIME" in dic_agent_conf_extra:
        dic_agent_conf_extra["FIXED_TIME"] = [15, 15, 15, 15, 15, 15, 15, 15]
    deploy_dic_agent_conf = merge(DIC_BASE_AGENT_CONF, dic_agent_conf_extra)

    # Set up environment config
    dic_traffic_env_conf_extra = {
        "W": 1,
        "NUM_ROUNDS": args.num_rounds,
        "NUM_GENERATORS": args.gen,
        "NUM_AGENTS": 1 if args.model in LIST_SINGLE_MODEL else num_intersections,
        "NUM_INTERSECTIONS": num_intersections,
        "RUN_COUNTS": timeline["development_duration"],
        "SIMULATION_TIME": count,
        "DEVELOPMENT_DURATION": timeline["development_duration"],
        "FINAL_START_TIME": timeline["final_start_time"],
        "FINAL_DURATION": timeline["final_duration"],
        "CHECKPOINT_INTERVAL": timeline["checkpoint_interval"],
        "DEFAULT_STEP_SIZE": args.duration,
        "GREEN_TIME": args.duration - 5,
        "YELLOW_TIME": 5,
        "MIN_ACTION_TIME": args.duration,
        "MEASURE_TIME": args.duration,
        "REWARD_AGGREGATION": "average",
        "ENABLE_DETAILED_LOGGING": True,

        "MODEL_NAME": args.model,
        "MODEL": args.model,
        "PROJECT_NAME": args.proj_name,
        "USE_WANDB": args.use_wandb,
        "TRAFFIC_FILE": args.traffic_file,
        "ROADNET_FILE": roadnet_file,

        "LIST_STATE_FEATURE": model_config["state_feature"],
        "DIC_REWARD_INFO": model_config["reward_info"],
    }

    # Add model-specific env configs
    if "additional_env_config" in model_config:
        dic_traffic_env_conf_extra.update(model_config["additional_env_config"])

    if args.eightphase:
        dic_traffic_env_conf_extra["PHASE"] = {
            1: [0, 1, 0, 1, 0, 0, 0, 0],
            2: [0, 0, 0, 0, 0, 1, 0, 1],
            3: [1, 0, 1, 0, 0, 0, 0, 0],
            4: [0, 0, 0, 0, 1, 0, 1, 0],
            5: [1, 1, 0, 0, 0, 0, 0, 0],
            6: [0, 0, 1, 1, 0, 0, 0, 0],
            7: [0, 0, 0, 0, 0, 0, 1, 1],
            8: [0, 0, 0, 0, 1, 1, 0, 0]
        }
        dic_traffic_env_conf_extra["PHASE_LIST"] = ['WT_ET', 'NT_ST', 'WL_EL', 'NL_SL',
                                                    'WL_WT', 'EL_ET', 'SL_ST', 'NL_NT']

    memo = args.memo or args.model
    timestamp = time.strftime('%m_%d_%H_%M_%S', time.localtime(time.time()))
    dic_path_extra = {
        "PATH_TO_MODEL": os.path.join("model", memo, args.traffic_file + "_" + timestamp),
        "PATH_TO_WORK_DIRECTORY": os.path.join("records", memo, args.traffic_file + "_" + timestamp),
        "PATH_TO_DATA": os.path.join("data", template, str(road_net)),
        "PATH_TO_ERROR": os.path.join("errors", memo)
    }

    deploy_dic_traffic_env_conf = merge(RL_BASE_ENV_CONF, dic_traffic_env_conf_extra)
    deploy_dic_path = merge(DIC_PATH, dic_path_extra)

    pipeline = Pipeline(
        dic_agent_conf=deploy_dic_agent_conf,
        dic_traffic_env_conf=deploy_dic_traffic_env_conf,
        dic_path=deploy_dic_path,
        roadnet=f'{template}-{road_net}',
        trafficflow=args.traffic_file.split(".")[0],
    )
    pipeline.run(round=0, multi_process=False)
    print(f"Checkpoints: {deploy_dic_path['PATH_TO_MODEL']}")
    print(
        "Evaluate with: python -m baselines.run_baseline --baseline "
        f"{args.model.lower()} --rl_checkpoint {deploy_dic_path['PATH_TO_MODEL']}"
    )


if __name__ == "__main__":
    main()
