"""RL baseline evaluation controller unit tests (no network, no SUMO, no TF)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from baselines.rl import eval_controller
from baselines.rl.eval_controller import (
    RLBaselineController,
    highest_available_round,
)


class StubAgent:
    """Records construction and replays positional canonical actions."""

    last_instance = None

    def __init__(self, dic_agent_conf, dic_traffic_env_conf, dic_path, cnt_round,
                 intersection_id="0"):
        self.dic_agent_conf = dic_agent_conf
        self.dic_traffic_env_conf = dic_traffic_env_conf
        self.dic_path = dic_path
        self.cnt_round = cnt_round
        self.intersection_id = intersection_id
        self.seen_state = None
        StubAgent.last_instance = self

    def choose_action(self, step, state):
        self.seen_state = state
        return [index % 4 for index in range(len(state))]


class FakeIntersection:
    def __init__(self, inter_id, local_map):
        self.inter_id = inter_id
        self._local_map = local_map

    def _get_four_phase(self):
        return (self._local_map, {}, [])


class FakeEnv:
    def __init__(self, intersections, state):
        self.list_intersection = intersections
        self._state = state
        self.requested_features = None

    def get_state(self, features):
        self.requested_features = list(features)
        return self._state, False


def make_checkpoint_dir(tmp_path, rounds=(3, 1)):
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    for round_index in rounds:
        (checkpoint_dir / f"round_{round_index}_inter_0.h5").touch()
    return str(checkpoint_dir)


def make_controller(tmp_path, monkeypatch, rounds=(3, 1), agent_conf=None, **kwargs):
    monkeypatch.setitem(eval_controller.DIC_AGENTS, "Colight", StubAgent)
    checkpoint_dir = make_checkpoint_dir(tmp_path, rounds)
    if agent_conf is not None:
        (tmp_path / "checkpoints" / "agent.conf").write_text(
            json.dumps(agent_conf), encoding="utf-8"
        )
    return RLBaselineController(
        model_name="Colight",
        checkpoint_dir=checkpoint_dir,
        env_config={"PHASE": {0: [0, 1]}, "SEED": 1},
        **kwargs,
    )


class TestRoundSelection:
    def test_highest_round_found(self, tmp_path):
        assert highest_available_round(make_checkpoint_dir(tmp_path, (3, 1, 7))) == 7

    def test_pt_checkpoints_count(self, tmp_path):
        checkpoint_dir = tmp_path / "pt"
        checkpoint_dir.mkdir()
        (checkpoint_dir / "round_5_inter_0.pt").touch()
        assert highest_available_round(str(checkpoint_dir)) == 5

    def test_empty_checkpoint_dir_rejected(self, tmp_path):
        checkpoint_dir = tmp_path / "empty"
        checkpoint_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            highest_available_round(str(checkpoint_dir))

    def test_default_round_is_the_highest(self, tmp_path, monkeypatch):
        controller = make_controller(tmp_path, monkeypatch, rounds=(2, 9))
        assert controller.round_index == 9
        assert StubAgent.last_instance.cnt_round == 10  # round + 1 loading path

    def test_explicit_round(self, tmp_path, monkeypatch):
        controller = make_controller(tmp_path, monkeypatch, rounds=(2, 9), round_index=2)
        assert controller.round_index == 2
        assert StubAgent.last_instance.cnt_round == 3


class TestAgentConstruction:
    def test_epsilon_forced_to_zero(self, tmp_path, monkeypatch):
        make_controller(tmp_path, monkeypatch)
        assert StubAgent.last_instance.dic_agent_conf["EPSILON"] == 0
        assert StubAgent.last_instance.dic_agent_conf["MIN_EPSILON"] == 0

    def test_agent_conf_from_checkpoint_dir_overrides(self, tmp_path, monkeypatch):
        make_controller(tmp_path, monkeypatch, agent_conf={"D_DENSE": 99})
        assert StubAgent.last_instance.dic_agent_conf["D_DENSE"] == 99
        # Deterministic evaluation still wins over the file's epsilon.
        assert StubAgent.last_instance.dic_agent_conf["EPSILON"] == 0

    def test_agent_env_view_carries_model_features(self, tmp_path, monkeypatch):
        make_controller(tmp_path, monkeypatch)
        env_conf = StubAgent.last_instance.dic_traffic_env_conf
        assert env_conf["NUM_AGENTS"] == 1
        assert env_conf["LIST_STATE_FEATURE"] == [
            "cur_phase_four", "lane_num_vehicle", "adjacency_matrix",
        ]

    def test_citylight_device_routing(self, tmp_path, monkeypatch):
        monkeypatch.setitem(eval_controller.DIC_AGENTS, "CityLight", StubAgent)
        checkpoint_dir = make_checkpoint_dir(tmp_path, (0,))
        RLBaselineController(
            model_name="CityLight",
            checkpoint_dir=checkpoint_dir,
            env_config={},
            device="cpu",
        )
        assert StubAgent.last_instance.dic_agent_conf["CITYLIGHT_DEVICE"] == "cpu"

    def test_missing_checkpoint_dir_rejected(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            RLBaselineController(
                model_name="Colight",
                checkpoint_dir=str(tmp_path / "absent"),
                env_config={},
            )


class TestDecide:
    def make_env(self):
        # Intersection 0 supports canonical phases {0, 1, 3} (three local
        # phases); intersection 1 supports all four canonical phases.
        intersections = [
            FakeIntersection("A", {0: 0, 1: 1, 3: 2}),
            FakeIntersection("B", {0: 0, 1: 1, 2: 2, 3: 3}),
        ]
        state = [
            {"cur_phase_four": [0, 0, 1, 0], "lane_num_vehicle": [1] * 12},
            {"cur_phase_four": [1, 0, 0, 0], "lane_num_vehicle": [2] * 12},
        ]
        observations = [
            SimpleNamespace(phases=["ETWT", "NTST", "NLSL"]),
            SimpleNamespace(phases=["ETWT", "NTST", "ELWL", "NLSL"]),
        ]
        return FakeEnv(intersections, state), observations

    def test_decide_requires_bound_env(self, tmp_path, monkeypatch):
        controller = make_controller(tmp_path, monkeypatch, round_index=3)
        with pytest.raises(RuntimeError, match="bind_env"):
            controller.decide([], 0)

    def test_canonical_to_local_mapping(self, tmp_path, monkeypatch):
        controller = make_controller(tmp_path, monkeypatch, round_index=3)
        env, observations = self.make_env()
        controller.bind_env(env)
        actions, traces = controller.decide(observations, 5)
        # Stub agent answers [0, 1]: canonical 0 -> local 0, canonical 1 -> local 1.
        assert actions == {"A": 0, "B": 1}
        # The state the agent saw is exactly what env.get_state returned.
        assert StubAgent.last_instance.seen_state is env._state
        assert env.requested_features == controller.state_features
        assert traces[0]["controller"] == "colight"
        assert traces[0]["canonical_action"] == 0
        assert traces[0]["local_action"] == 0
        assert traces[0]["signal"] == "ETWT"
        assert traces[0]["round"] == 3
        assert traces[0]["checkpoint"].endswith("checkpoints")
        assert traces[0]["fallback"] is None

    def test_unsupported_canonical_phase_maps_through(self, tmp_path, monkeypatch):
        controller = make_controller(tmp_path, monkeypatch, round_index=3)
        env, observations = self.make_env()
        controller.bind_env(env)
        # Force the stub to answer canonical 2 for both intersections.
        StubAgent.last_instance.choose_action = lambda step, state: [2, 2]
        actions, _ = controller.decide(observations, 6)
        # A: canonical 2 unsupported -> 2 % len(map)=2 -> passthrough 2.
        assert actions["A"] == 2
        # B: canonical 2 -> local 2.
        assert actions["B"] == 2

    def test_usage_summary_zeroed(self, tmp_path, monkeypatch):
        summary = make_controller(tmp_path, monkeypatch).usage_summary()
        assert summary == {
            "requests": 0,
            "failures": 0,
            "rate_limited": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_mean_s": None,
            "latency_max_s": None,
        }
