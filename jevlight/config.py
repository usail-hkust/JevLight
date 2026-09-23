"""Environment configuration and dataset registry.

``dic_traffic_env_conf`` and ``DIC_PATH`` are carried over verbatim from
ChatLight's ``utils/config.py`` (data only; the model-list keys are inert
here).  The dataset registry mirrors ``run_LLMLight.setup_dataset_config``.
"""

from __future__ import annotations

from typing import Any, Dict


DIC_PATH: Dict[str, str] = {
    "PATH_TO_MODEL": "model/default",
    "PATH_TO_WORK_DIRECTORY": "records/default",
    "PATH_TO_DATA": "data/template",
    "PATH_TO_PRETRAIN_MODEL": "model/default",
    "PATH_TO_ERROR": "errors/default",
}


dic_traffic_env_conf: Dict[str, Any] = {
    "NUM_LANE": 12,
    # 'WT_ET', 'NT_ST', 'WL_EL', 'NL_SL'/ 'WL_WT', 'EL_ET', 'SL_ST', 'NL_NT'
    "PHASE_MAP": [[1, 4, 12, 13, 14, 15, 16, 17], [7, 10, 18, 19, 20, 21, 22, 23], [0, 3, 18, 19, 20, 21, 22, 23], [6, 9, 12, 13, 14, 15, 16, 17]],
    "FORGET_ROUND": 20,
    "RUN_COUNTS": 3600,
    "MODEL_NAME": None,
    "TOP_K_ADJACENCY": 5,
    "ACTION_PATTERN": "set",
    "NUM_INTERSECTIONS": 1,
    "OBS_LENGTH": 167,
    "GREEN_TIME": 10,
    "YELLOW_TIME": 5,
    "MIN_ACTION_TIME": 15,
    "MEASURE_TIME": 15,
    "REWARD_AGGREGATION": "average",
    "BOUNDARY_FEATURES_IN_DETAILED_MODE": False,
    "BINARY_PHASE_EXPANSION": True,
    "NUM_PHASES": 4,
    "NUM_LANES": [3, 3, 3, 3],
    "INTERVAL": 1,
    "LIST_STATE_FEATURE": [
        "cur_phase",
        "cur_phase_four",
        "time_this_phase",
        "lane_num_vehicle",
        "lane_num_vehicle_downstream",
        "traffic_movement_pressure_num",
        "traffic_movement_pressure_queue",
        "traffic_movement_pressure_queue_efficient",
        "pressure",
        "adjacency_matrix",
    ],
    "DIC_REWARD_INFO": {
        "queue_length": 0,
        "pressure": 0,
    },
    "PHASE": {
        0: [0, 1, 0, 1, 0, 0, 0, 0],
        1: [0, 0, 0, 0, 0, 1, 0, 1],
        2: [1, 0, 1, 0, 0, 0, 0, 0],
        3: [0, 0, 0, 0, 1, 0, 1, 0],
    },
    "list_lane_order": ["WL", "WT", "EL", "ET", "NL", "NT", "SL", "ST"],
    "PHASE_LIST": ["WT_ET", "NT_ST", "WL_EL", "NL_SL"],
    "INTER_PHASE_MAPPING": {0: ["ETWT", "NTST", "ELWL", "NLSL"]},
}


EIGHT_PHASE_PHASES = {
    0: [0, 1, 0, 1, 0, 0, 0, 0],
    1: [0, 0, 0, 0, 0, 1, 0, 1],
    2: [1, 0, 1, 0, 0, 0, 0, 0],
    3: [0, 0, 0, 0, 1, 0, 1, 0],
    4: [1, 1, 0, 0, 0, 0, 0, 0],
    5: [0, 0, 1, 1, 0, 0, 0, 0],
    6: [0, 0, 0, 0, 0, 0, 1, 1],
    7: [0, 0, 0, 0, 1, 1, 0, 0],
}
EIGHT_PHASE_LIST = [
    "WT_ET", "NT_ST", "WL_EL", "NL_SL",
    "WL_WT", "EL_ET", "SL_ST", "NL_NT",
]


DATASETS: Dict[str, Dict[str, Any]] = {
    "jinan": {
        "template": "Jinan",
        "road_net": "3_4",
        "roadnet_file": "roadnet_3_4.net.xml",
        "traffic_files": [
            "anon_3_4_jinan_real.rou.xml",
            "anon_3_4_jinan_real_2000.rou.xml",
            "anon_3_4_jinan_real_2500.rou.xml",
            "anon_3_4_jinan_synthetic_24000_60min.rou.xml",
            "anon_3_4_jinan_synthetic_24h_6000.rou.xml",
        ],
        "num_intersections": 12,
    },
    # Drop the ChatLight dataset folders under data/ to enable these.
    "hangzhou": {
        "template": "Hangzhou",
        "road_net": "4_4",
        "roadnet_file": "roadnet_4_4.net.xml",
        "traffic_files": [
            "anon_4_4_hangzhou_real.rou.xml",
            "anon_4_4_hangzhou_real_5816.rou.xml",
            "anon_4_4_hangzhou_synthetic_24000_60min.rou.xml",
        ],
        "num_intersections": 16,
    },
    "newyork": {
        "template": "NewYork",
        "road_net": "28_7",
        "roadnet_file": "roadnet_28_7.net.xml",
        "traffic_files": [
            "anon_28_7_newyork_real_double.rou.xml",
            "anon_28_7_newyork_real_triple.rou.xml",
        ],
        "num_intersections": 196,
    },
    "mzw": {
        "template": "MZW",
        "road_net": "44/daily_sumo",
        "roadnet_file": "mzwmap_phase.net.xml",
        "traffic_files": ["mzwmap_0905_0101.vehicles.rou.xml"],
        "num_intersections": 44,
    },
}


class DatasetException(Exception):
    """Raised when a requested dataset is not registered."""


def setup_dataset_config(dataset: str) -> Dict[str, Any]:
    dataset = dataset.strip().lower()
    if dataset in ("newyork_28x7",):
        dataset = "newyork"
    if dataset not in DATASETS:
        raise DatasetException(
            f"Dataset {dataset} does not exist. Registered: "
            + ", ".join(sorted(DATASETS))
        )
    config = dict(DATASETS[dataset])
    available = [
        name
        for name in config["traffic_files"]
        if _dataset_file_exists(config, name)
    ]
    if available:
        config["traffic_files"] = available
    return config


def _dataset_file_exists(dataset_config: Dict[str, Any], traffic_file: str) -> bool:
    import os

    path = os.path.join(
        "data",
        dataset_config["template"],
        str(dataset_config["road_net"]),
        traffic_file,
    )
    return os.path.isfile(path)
