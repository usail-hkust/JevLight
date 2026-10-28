"""RL baseline evaluation controller for the baselines runner.

Wraps a trained agent (``baselines.rl.train`` checkpoint) behind the JevLight
controller contract.  Feature parity with training is structural: ``decide``
reads the canonical env state features via ``env.get_state`` at exactly the
instant the ported ``Generator``/``model_test`` would (the features cached at
the end of the previous ``env.step``), applies the same single-agent network
call, and maps canonical actions to local phase indices with the same
``_map_action_for_intersection`` logic (ported from
``utils/model_test.py:21-31``).

Checkpoint selection constructs the agent with ``cnt_round = round + 1`` so
``NetworkAgent.__init__``/``CityLightAgent.__init__`` load
``round_<round>_inter_0`` directly, avoiding the ``cnt_round == 0``
force-load path (a non-empty model directory would make it load
``round_0_inter_0`` regardless of the requested round).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from baselines.rl.rl_config import (
    DIC_AGENTS,
    DIC_BASE_AGENT_CONF,
    get_model_config,
)
from baselines.rl.pipeline.pipeline import merge


CHECKPOINT_PATTERN = re.compile(r"^round_(\d+)_inter_0\.(h5|pt)$")


def _map_action_for_intersection(env, intersection_idx, action, model_name=None):
    """Canonical -> local action index (verbatim model_test.py:21-31)."""
    local_action_map = env.list_intersection[intersection_idx]._get_four_phase()[0]
    if not local_action_map:
        return 0
    if model_name == "CityLight":
        canonical_action = int(action)
        if canonical_action in local_action_map:
            return local_action_map[canonical_action]
        return local_action_map[min(local_action_map)]
    canonical_action = int(action) % len(local_action_map)
    return local_action_map.get(canonical_action, canonical_action)


def highest_available_round(checkpoint_dir: str) -> int:
    """Highest ``round_*_inter_0`` index present in the checkpoint directory."""
    rounds = []
    for name in os.listdir(checkpoint_dir):
        match = CHECKPOINT_PATTERN.match(name)
        if match:
            rounds.append(int(match.group(1)))
    if not rounds:
        raise FileNotFoundError(
            f"No round_*_inter_0.h5/.pt checkpoints found in {checkpoint_dir}"
        )
    return max(rounds)


class RLBaselineController:
    """A trained RL agent as a JevLight runner controller."""

    def __init__(
        self,
        model_name: str,
        checkpoint_dir: str,
        round_index: Optional[int] = None,
        agent_conf_path: Optional[str] = None,
        env_config: Optional[Dict[str, Any]] = None,
        device: str = "auto",
    ):
        if model_name not in DIC_AGENTS:
            raise ValueError(
                f"Unknown RL model {model_name!r}; registered: {', '.join(DIC_AGENTS)}"
            )
        if not os.path.isdir(checkpoint_dir):
            raise FileNotFoundError(f"Checkpoint directory does not exist: {checkpoint_dir}")
        self.model_name = model_name
        self.checkpoint_dir = checkpoint_dir
        self.round_index = (
            highest_available_round(checkpoint_dir)
            if round_index is None
            else int(round_index)
        )

        model_config = get_model_config(model_name)
        self.state_features = list(model_config["state_feature"])

        dic_agent_conf = merge(DIC_BASE_AGENT_CONF, model_config["agent_config"])
        conf_path = agent_conf_path
        if conf_path is None:
            candidate = os.path.join(checkpoint_dir, "agent.conf")
            if os.path.isfile(candidate):
                conf_path = candidate
        if conf_path is not None:
            with open(conf_path, "r") as f:
                dic_agent_conf.update(json.load(f))
        if model_name == "CityLight":
            # --rl_device routing; the agent resolves "auto" itself.
            dic_agent_conf["CITYLIGHT_DEVICE"] = device
        # Deterministic evaluation, mirroring model_test.py:80-82.
        dic_agent_conf["EPSILON"] = 0
        dic_agent_conf["MIN_EPSILON"] = 0

        # Metadata-only agent view of the environment: the runner's env config
        # (JevLight parity) plus the model's own state features and
        # TOP_K_ADJACENCY (CoLight's _cal_len_feature reads LIST_STATE_FEATURE;
        # the adjacency matrix shape must match training).
        agent_env_conf = dict(env_config or {})
        agent_env_conf["NUM_AGENTS"] = 1
        agent_env_conf["LIST_STATE_FEATURE"] = list(self.state_features)
        agent_env_conf.update(model_config.get("additional_env_config", {}))

        dic_path = {
            "PATH_TO_MODEL": checkpoint_dir,
            "PATH_TO_WORK_DIRECTORY": checkpoint_dir,
            "PATH_TO_DATA": agent_env_conf.get("PATH_TO_DATA", "data"),
        }
        self.agent = DIC_AGENTS[model_name](
            dic_agent_conf=dic_agent_conf,
            dic_traffic_env_conf=agent_env_conf,
            dic_path=dic_path,
            cnt_round=self.round_index + 1,
            intersection_id="0",
        )
        self.env = None

    def bind_env(self, env) -> None:
        """Attach the runner's SUMOEnv for canonical state feature reads."""
        self.env = env

    @property
    def controller_name(self) -> str:
        return self.model_name.lower()

    def decide(
        self,
        observations: Sequence[Any],
        step: int,
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
        if self.env is None:
            raise RuntimeError("RLBaselineController requires bind_env(env) before decide()")
        state, _ = self.env.get_state(self.state_features)
        canonical_actions = self.agent.choose_action(step, state)

        actions: Dict[str, int] = {}
        traces: List[Dict[str, Any]] = []
        for idx, intersection in enumerate(self.env.list_intersection):
            canonical = int(canonical_actions[idx])
            local = _map_action_for_intersection(
                self.env, idx, canonical, self.model_name
            )
            actions[intersection.inter_id] = local
            phases = observations[idx].phases if idx < len(observations) else []
            signal = (
                phases[local % len(phases)]
                if phases
                else str(canonical)
            )
            traces.append({
                "step": step,
                "intersection": intersection.inter_id,
                "controller": self.controller_name,
                "agent_mode": self.controller_name,
                "packaging": "none",
                "transport": "local",
                "model": self.model_name,
                "canonical_action": canonical,
                "local_action": local,
                "signal": signal,
                "checkpoint": self.checkpoint_dir,
                "round": self.round_index,
                "fallback": None,
            })
        return actions, traces

    def usage_summary(self) -> Dict[str, Any]:
        return {
            "requests": 0,
            "failures": 0,
            "rate_limited": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_mean_s": None,
            "latency_max_s": None,
        }
