"""RL baseline configuration unit tests (no network, no SUMO)."""

from __future__ import annotations

import pytest

from baselines.rl import rl_config


class TestGetModelConfig:
    def test_covers_the_six_models(self):
        for name in ("Colight", "PressLight", "MPLight", "Attend", "AdvancedDQN", "CityLight"):
            config = rl_config.get_model_config(name)
            assert config["state_feature"]
            assert config["reward_info"]
            assert config["wrapper"] == "pipeline"

    def test_colight_features_and_reward(self):
        config = rl_config.get_model_config("Colight")
        assert config["state_feature"] == [
            "cur_phase_four", "lane_num_vehicle", "adjacency_matrix",
        ]
        assert config["reward_info"] == {"queue_length": -0.25}
        assert config["agent_config"] == {"CNN_layers": [[32, 32]]}

    def test_presslight_and_mplight_features(self):
        assert rl_config.get_model_config("PressLight")["state_feature"] == [
            "cur_phase_four", "traffic_movement_pressure_queue",
        ]
        assert rl_config.get_model_config("PressLight")["additional_env_config"] == {
            "TOP_K_ADJACENCY": 5,
        }
        assert rl_config.get_model_config("MPLight")["state_feature"] == [
            "cur_phase_four", "traffic_movement_pressure_num",
        ]

    def test_attend_and_advanced_dqn_features(self):
        assert rl_config.get_model_config("Attend")["state_feature"] == ["num_in_seg_attend"]
        assert rl_config.get_model_config("AdvancedDQN")["state_feature"] == [
            "cur_phase_four",
            "traffic_movement_pressure_queue_efficient",
            "lane_enter_running_part",
        ]

    def test_citylight_config(self):
        config = rl_config.get_model_config("CityLight")
        assert config["state_feature"] == [
            "cur_phase_four",
            "traffic_movement_pressure_queue_efficient",
            "lane_num_waiting_vehicle_in",
            "adjacency_matrix",
            "citylight_observation",
            "citylight_available_actions",
            "citylight_local_queue",
            "citylight_neighbor_indices",
            "citylight_neighbor_mask",
            "citylight_neighbor_types",
            "citylight_neighbor_relations",
            "citylight_neighbor_distances",
        ]
        assert config["reward_info"] == {"queue_length": -1.0}
        assert config["agent_config"]["CITYLIGHT_LR"] == 0.0005
        assert config["agent_config"]["CITYLIGHT_PPO_EPOCHS"] == 10
        assert config["agent_config"]["EPSILON"] == 1
        assert config["additional_env_config"] == {"TOP_K_ADJACENCY": 5}

    def test_unknown_model_falls_back_to_colight(self):
        assert rl_config.get_model_config("Nope")["wrapper"] == "pipeline"


class TestRegistries:
    def test_dic_agents_maps_the_six_names(self):
        assert set(rl_config.DIC_AGENTS) == {
            "Colight", "PressLight", "MPLight", "Attend", "AdvancedDQN", "CityLight",
        }
        for agent_class in rl_config.DIC_AGENTS.values():
            assert callable(agent_class)

    def test_list_registries_cover_the_six_models(self):
        for registry in (
            rl_config.LIST_MODEL,
            rl_config.LIST_MODEL_NEED_TO_UPDATE,
            rl_config.LIST_SINGLE_MODEL,
        ):
            assert set(registry) == set(rl_config.DIC_AGENTS)

    def test_base_agent_conf_matches_the_source(self):
        assert rl_config.DIC_BASE_AGENT_CONF == {
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

    def test_rl_base_env_conf_extends_jevlight_with_list_keys(self):
        from jevlight.config import dic_traffic_env_conf

        for key, value in dic_traffic_env_conf.items():
            assert rl_config.RL_BASE_ENV_CONF[key] == value
        for key in ("LIST_MODEL", "LIST_MODEL_NEED_TO_UPDATE", "LIST_SINGLE_MODEL"):
            assert key in rl_config.RL_BASE_ENV_CONF


class TestTimeline:
    def test_short_simulation_is_all_development(self):
        timeline = rl_config.split_simulation_timeline(3600)
        assert timeline == {
            "development_duration": 3600,
            "final_start_time": 0,
            "final_duration": 3600,
            "checkpoint_interval": 3600,
        }

    def test_multiday_simulation_splits_40_60(self):
        timeline = rl_config.split_simulation_timeline(86400 * 2)
        assert timeline["development_duration"] == int(86400 * 2 * 0.4)
        assert timeline["final_start_time"] == int(86400 * 2 * 0.4)
        assert timeline["final_duration"] == 86400 * 2 - timeline["final_start_time"]

    def test_nonpositive_rejected(self):
        with pytest.raises(ValueError):
            rl_config.split_simulation_timeline(0)


class TestGuardedImports:
    def test_citylight_loads_with_torch(self):
        torch = pytest.importorskip("torch")
        from baselines.rl.pipeline.models.citylight_agent import CityLightAgent

        assert rl_config.DIC_AGENTS["CityLight"] is CityLightAgent
        assert torch is not None

    def test_tf_agents_are_stubs_without_tensorflow(self):
        import importlib.util

        if importlib.util.find_spec("tensorflow") is not None:
            pytest.skip("TensorFlow installed; stubs are inactive")
        with pytest.raises(ImportError, match="baselines-rl"):
            rl_config.DIC_AGENTS["Colight"]({"D_DENSE": 1}, {}, {}, 0, "0")
