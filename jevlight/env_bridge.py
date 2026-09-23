"""Minimal SUMO environment bridge.

ChatLight drives ``SUMOEnv`` through ``llm_agent.utils.env.InteractionEnv``,
which layers auto-agent orchestration (road graphs, heuristic fallbacks, OD
tracking) on top.  JevLight only needs the plain control loop, so this bridge
replicates InteractionEnv's essential setup — create the work directories,
dump the run configuration, construct ``SUMOEnv``, reset — and nothing else.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from utils.sumo_env import SUMOEnv


class JevLightEnv:
    """Owns one ``SUMOEnv`` and exposes the control-loop surface."""

    def __init__(
        self,
        dic_agent_conf: Dict[str, Any],
        dic_traffic_env_conf: Dict[str, Any],
        dic_path: Dict[str, str],
        trafficflow: str,
    ):
        self.dic_agent_conf = dic_agent_conf
        self.dic_traffic_env_conf = dic_traffic_env_conf
        self.dic_path = dic_path
        self.trafficflow = trafficflow
        self.env: SUMOEnv = None
        self._path_check(dic_path)
        self._copy_conf_file(dic_path, dic_agent_conf, dic_traffic_env_conf)
        self.env = SUMOEnv(
            path_to_log=dic_path["PATH_TO_WORK_DIRECTORY"],
            path_to_work_directory=dic_path["PATH_TO_WORK_DIRECTORY"],
            dic_traffic_env_conf=dic_traffic_env_conf,
            dic_path=dic_path,
        )
        self.env.reset()

    @staticmethod
    def _path_check(dic_path: Dict[str, str]) -> None:
        os.makedirs(dic_path["PATH_TO_WORK_DIRECTORY"], exist_ok=True)
        os.makedirs(dic_path["PATH_TO_MODEL"], exist_ok=True)
        os.makedirs(dic_path["PATH_TO_ERROR"], exist_ok=True)

    @staticmethod
    def _copy_conf_file(
        dic_path: Dict[str, str],
        dic_agent_conf: Dict[str, Any],
        dic_traffic_env_conf: Dict[str, Any],
    ) -> None:
        path = dic_path["PATH_TO_WORK_DIRECTORY"]
        with open(os.path.join(path, "agent.conf"), "w") as agent_file:
            json.dump(dic_agent_conf, agent_file, indent=4)
        with open(
            os.path.join(path, "traffic_env.conf"), "w"
        ) as env_file:
            json.dump(dic_traffic_env_conf, env_file, indent=4)

    def reset_env_with_start_time(self, start_time: int) -> None:
        """Restart the simulation beginning at ``start_time`` seconds."""
        self.env._start_time = start_time
        self.env.reset()
