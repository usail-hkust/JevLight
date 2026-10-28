"""RL baseline configuration.

Agent registries, the base agent hyperparameters, per-model state features
and rewards, and the training timeline split.  The traffic environment base
configuration is JevLight's own ``jevlight.config.dic_traffic_env_conf``
extended with the three RL list keys JevLight does not define.

Importing this module registers the agents: TensorFlow models load only when
TensorFlow is installed (targeted ``ImportError`` stubs otherwise), and
CityLight additionally needs torch.
"""

from jevlight.config import dic_traffic_env_conf as _jevlight_traffic_env_conf


def _missing_tensorflow_agent(model_name, import_error):
    class MissingTensorFlowAgent:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            raise ImportError(
                f"{model_name} requires TensorFlow; install the project's "
                "baselines-rl extra (tensorflow-cpu) before selecting this model"
            ) from import_error

    MissingTensorFlowAgent.__name__ = f"Unavailable{model_name}Agent"
    return MissingTensorFlowAgent


def _missing_torch_agent(model_name, import_error):
    class MissingTorchAgent:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            raise ImportError(
                f"{model_name} requires PyTorch; install the project's "
                "baselines-rl-torch extra before selecting this model"
            ) from import_error

    MissingTorchAgent.__name__ = f"Unavailable{model_name}Agent"
    return MissingTorchAgent


# CityLight is PyTorch-native and should remain usable without importing the
# legacy TensorFlow agents.  Keep their normal registrations when TensorFlow is
# installed and provide a targeted error only if one of them is selected.
try:
    from baselines.rl.pipeline.models.mplight_agent import MPLightAgent
    from baselines.rl.pipeline.models.colight_agent import CoLightAgent
    from baselines.rl.pipeline.models.presslight_one import PressLightAgentOne
    from baselines.rl.pipeline.models.advanced_mplight_agent import AdvancedMPLightAgent
    from baselines.rl.pipeline.models.simple_dqn_one import SimpleDQNAgentOne
    from baselines.rl.pipeline.models.attendlight_agent import AttendLightAgent
except ModuleNotFoundError as tensorflow_import_error:
    if not (
        tensorflow_import_error.name
        and tensorflow_import_error.name.startswith("tensorflow")
    ):
        raise
    MPLightAgent = _missing_tensorflow_agent("MPLight", tensorflow_import_error)
    CoLightAgent = _missing_tensorflow_agent("CoLight", tensorflow_import_error)
    PressLightAgentOne = _missing_tensorflow_agent("PressLight", tensorflow_import_error)
    AdvancedMPLightAgent = _missing_tensorflow_agent(
        "AdvancedMPLight", tensorflow_import_error
    )
    SimpleDQNAgentOne = _missing_tensorflow_agent("DQN", tensorflow_import_error)
    AttendLightAgent = _missing_tensorflow_agent("Attend", tensorflow_import_error)

try:
    from baselines.rl.pipeline.models.citylight_agent import CityLightAgent
except ModuleNotFoundError as torch_import_error:
    if not (
        torch_import_error.name
        and torch_import_error.name.startswith("torch")
    ):
        raise
    CityLightAgent = _missing_torch_agent("CityLight", torch_import_error)


DIC_AGENTS = {
    "Colight": CoLightAgent,
    "PressLight": PressLightAgentOne,
    "MPLight": MPLightAgent,
    "Attend": AttendLightAgent,
    "AdvancedDQN": SimpleDQNAgentOne,
    "CityLight": CityLightAgent,
}

# The three RL registry lists from utils/config.py's dic_traffic_env_conf,
# restricted to the ported model set.
LIST_MODEL = ["Colight", "PressLight", "MPLight", "Attend", "AdvancedDQN", "CityLight"]
LIST_MODEL_NEED_TO_UPDATE = [
    "Colight", "PressLight", "MPLight", "Attend", "AdvancedDQN", "CityLight",
]
LIST_SINGLE_MODEL = [
    "Colight", "PressLight", "MPLight", "Attend", "AdvancedDQN", "CityLight",
]

DIC_BASE_AGENT_CONF = {
    "D_DENSE": 20,
    "LEARNING_RATE": 0.001,
    "PATIENCE": 10,
    "BATCH_SIZE": 20,
    "EPOCHS": 100,
    "SAMPLE_SIZE": 3000,
    "MAX_MEMORY_LEN": 12000,

    "UPDATE_Q_BAR_FREQ": 5,
    "UPDATE_Q_BAR_EVERY_C_ROUND": False,

    "GAMMA": 0.8,
    "NORMAL_FACTOR": 20,

    "EPSILON": 0.8,
    "EPSILON_DECAY": 0.95,
    "MIN_EPSILON": 0.2,
    "LOSS_FUNCTION": "mean_squared_error",
}

DIC_FIXEDTIME_AGENT_CONF = {
    "FIXED_TIME": [15, 15, 15, 15]
}

# JevLight's env base configuration plus the three RL list keys it does not
# define.
RL_BASE_ENV_CONF = dict(_jevlight_traffic_env_conf)
RL_BASE_ENV_CONF.update({
    "LIST_MODEL": list(LIST_MODEL),
    "LIST_MODEL_NEED_TO_UPDATE": list(LIST_MODEL_NEED_TO_UPDATE),
    "LIST_SINGLE_MODEL": list(LIST_SINGLE_MODEL),
})

SECONDS_PER_DAY = 24 * 60 * 60
CHECKPOINT_INTERVAL = 60 * 60


def split_simulation_timeline(simulation_time):
    """Match run_auto_agent.py's development/final split."""
    if simulation_time <= 0:
        raise ValueError("simulation_time must be positive")

    if simulation_time > SECONDS_PER_DAY:
        development_duration = int(simulation_time * 0.4)
        final_start_time = development_duration
    else:
        development_duration = simulation_time
        final_start_time = 0

    return {
        "development_duration": development_duration,
        "final_start_time": final_start_time,
        "final_duration": simulation_time - final_start_time,
        "checkpoint_interval": CHECKPOINT_INTERVAL,
    }


def get_model_config(model_name):
    """Get model-specific configurations (run_RLLight.py:165-322, verbatim)."""
    model_configs = {
        "Colight": {
            "agent_config": {
                "CNN_layers": [[32, 32]],
            },
            "state_feature": [
                "cur_phase_four",
                "lane_num_vehicle",
                "adjacency_matrix",
            ],
            "reward_info": {"queue_length": -0.25},
            "wrapper": "pipeline"
        },
        "PressLight": {
            "agent_config": {},
            "state_feature": [
                "cur_phase_four",
                "traffic_movement_pressure_queue",
            ],
            "reward_info": {"pressure": -0.25},
            "wrapper": "pipeline",
            "additional_env_config": {
                "TOP_K_ADJACENCY": 5,
            }
        },
        "MPLight": {
            "agent_config": {},
            "state_feature": [
                "cur_phase_four",
                "traffic_movement_pressure_num",
            ],
            "reward_info": {"pressure": -0.25},
            "wrapper": "pipeline"
        },
        "Attend": {
            "agent_config": {},
            "state_feature": [
                "num_in_seg_attend",
            ],
            "reward_info": {"pressure": -0.25},
            "wrapper": "pipeline"
        },
        "AdvancedDQN": {
            "agent_config": {},
            "state_feature": [
                "cur_phase_four",
                "traffic_movement_pressure_queue_efficient",
                "lane_enter_running_part",
            ],
            "reward_info": {"pressure": -0.25},
            "wrapper": "pipeline"
        },
        # Official CityLight MAPPO hyper-parameters (githubs/CityLight README,
        # jinan reproduction: --lr 5e-4 --critic_lr 5e-4 --ppo_epoch 10
        # --num_mini_batch 18 --layer_N 2 --alpha 0.2).  Signal execution
        # (15 s action with 5 s yellow) stays owned by this repository.
        "CityLight": {
            "agent_config": {
                "CITYLIGHT_LR": 0.0005,
                "CITYLIGHT_CRITIC_LR": 0.0005,
                "CITYLIGHT_OPT_EPS": 1e-5,
                "CITYLIGHT_CLIP_PARAM": 0.2,
                "CITYLIGHT_PPO_EPOCHS": 10,
                "CITYLIGHT_NUM_MINI_BATCH": 18,
                "CITYLIGHT_GAE_LAMBDA": 0.95,
                "CITYLIGHT_VALUE_LOSS_COEF": 1.0,
                "CITYLIGHT_ENTROPY_COEF": 0.01,
                "CITYLIGHT_MAX_GRAD_NORM": 10.0,
                "CITYLIGHT_NEIGHBOUR_REWARD_ALPHA": 0.2,
                "CITYLIGHT_SEED": 1,
                # >0 keeps rollouts stochastic during training; model_test
                # forces EPSILON=0 for deterministic evaluation.
                "EPSILON": 1,
                "GAMMA": 0.99,
            },
            "state_feature": [
                "cur_phase_four",
                "traffic_movement_pressure_queue_efficient",
                "lane_num_waiting_vehicle_in",
                "adjacency_matrix",
                # Official CityLight observation/graph features consumed by
                # citylight_agent.CityLightAgent.
                "citylight_observation",
                "citylight_available_actions",
                "citylight_local_queue",
                "citylight_neighbor_indices",
                "citylight_neighbor_mask",
                "citylight_neighbor_types",
                "citylight_neighbor_relations",
                "citylight_neighbor_distances",
            ],
            "reward_info": {"queue_length": -1.0},
            "wrapper": "pipeline",
            "additional_env_config": {
                "TOP_K_ADJACENCY": 5,
            },
        },
    }
    return model_configs.get(model_name, model_configs["Colight"])
