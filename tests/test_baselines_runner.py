"""Baselines runner unit tests (no network, no SUMO).

The drift-guard tests compare ``baselines.run_baseline.build_configs`` against
``run_jevlight.build_configs`` so the mirrored configuration cannot silently
diverge from the project's evaluation flow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_jevlight
from baselines import BASELINES, RL_BASELINES, RL_MODEL_NAMES, build_controller
from baselines.run_baseline import build_configs, parse_args
from jevlight.config import setup_dataset_config


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "drift_run"


def jev_args(extra):
    return run_jevlight.parse_args(["--dry_run", "--memo", "Drift", "--proj_name", "P", *extra])


def base_args(extra):
    return parse_args(["--baseline", "maxpressure", "--memo", "Drift", "--proj_name", "P", *extra])


class TestBuildConfigsDriftGuard:
    @pytest.mark.parametrize("extra", [
        [],
        ["--eightphase"],
        ["--count", "900", "--duration", "20", "--num_intersections", "12"],
    ])
    def test_env_config_and_paths_match_run_jevlight(self, extra):
        dataset_config = setup_dataset_config("jinan")
        jev_agent, jev_env, jev_paths = run_jevlight.build_configs(
            jev_args(extra), dataset_config, RUN_ID
        )
        base_agent, base_env, base_paths = build_configs(
            base_args(extra), dataset_config, RUN_ID
        )
        assert base_env.pop("MODEL_NAME") == "maxpressure"
        assert base_env.pop("MODEL") == "maxpressure"
        jev_env.pop("MODEL_NAME")
        jev_env.pop("MODEL")
        assert base_env == jev_env
        assert base_paths == jev_paths
        assert base_agent == {**jev_agent, "POLICY": "maxpressure"}

    def test_results_group_is_the_baseline_name(self):
        dataset_config = setup_dataset_config("jinan")
        _, _, paths = build_configs(
            parse_args(["--baseline", "webster", "--memo", "M"]), dataset_config, RUN_ID
        )
        assert paths["PATH_TO_WORK_DIRECTORY"] == f"results/webster/M/{RUN_ID}"
        assert paths["PATH_TO_MODEL"] == f"results/webster/M/{RUN_ID}/model"

    def test_memo_must_be_a_single_directory(self):
        dataset_config = setup_dataset_config("jinan")
        with pytest.raises(ValueError):
            build_configs(
                parse_args(["--baseline", "fixedtime", "--memo", "a/b"]),
                dataset_config,
                RUN_ID,
            )

    def test_evaluation_output_dir_must_stay_inside_results(self):
        args = parse_args([
            "--baseline", "fixedtime",
            "--evaluation_output_dir", str(REPO_ROOT / "records" / "elsewhere"),
        ])
        with pytest.raises(ValueError):
            build_configs(args, setup_dataset_config("jinan"), RUN_ID)


class TestParseArgs:
    def test_baseline_is_required(self):
        with pytest.raises(SystemExit):
            parse_args(["--count", "60"])

    def test_unknown_baseline_rejected(self):
        with pytest.raises(SystemExit):
            parse_args(["--baseline", "sotl"])

    def test_citylight_rejects_eightphase(self):
        with pytest.raises(SystemExit):
            parse_args(["--baseline", "citylight", "--eightphase"])

    def test_communication_threshold_bounds(self):
        with pytest.raises(SystemExit):
            parse_args(["--baseline", "collmlight", "--communication_threshold", "1.5"])

    def test_webster_cycle_bounds(self):
        with pytest.raises(SystemExit):
            parse_args(["--baseline", "webster", "--webster_min_cycle", "130"])

    def test_config_must_live_under_the_baseline_directory(self, tmp_path):
        config = tmp_path / "not_baselines.json"
        config.write_text('{"baseline": "fixedtime"}', encoding="utf-8")
        with pytest.raises(SystemExit):
            parse_args(["--config", str(config)])

    def test_config_baseline_must_match_parent_directory(self):
        with pytest.raises(SystemExit):
            parse_args([
                "--config", "baselines/config/fixedtime/jinan_smoke.json",
                "--baseline", "webster",
            ])

    def test_config_provides_defaults(self):
        args = parse_args(["--config", "baselines/config/fixedtime/jinan_smoke.json"])
        assert args.baseline == "fixedtime"
        assert args.count == 3600
        assert args.fixed_time_splits == "15,15,15,15"

    def test_cli_overrides_config(self):
        args = parse_args([
            "--config", "baselines/config/fixedtime/jinan_smoke.json",
            "--count", "60",
        ])
        assert args.count == 60

    def test_llm_defaults_are_none_until_resolved(self):
        args = parse_args(["--baseline", "collmlight"])
        assert args.max_tokens is None
        assert args.top_p is None
        assert args.backbone is None


class TestRegistry:
    def test_every_baseline_is_registered(self):
        assert set(BASELINES) == {
            "llmlight", "collmlight", "maxpressure", "webster", "fixedtime",
            "colight", "presslight", "mplight", "attendlight", "advanceddqn",
            "citylight",
        }

    def test_heuristic_controllers_resolve(self):
        args = SimpleNamespace(
            duration=15,
            fixed_time_splits="15,15,15,15",
            webster_update_frequency=60,
            webster_min_green=8.0,
            webster_min_cycle=32.0,
            webster_max_cycle=120.0,
            webster_saturation_flow=0.38,
            webster_vehicle_length=8.0,
        )
        from baselines.fixedtime import FixedTimeController
        from baselines.maxpressure import StrictLaneMaxPressureController
        from baselines.webster import WebsterController

        assert isinstance(
            build_controller("maxpressure", args, {}), StrictLaneMaxPressureController
        )
        assert isinstance(
            build_controller("fixedtime", args, {}), FixedTimeController
        )
        assert isinstance(build_controller("webster", args, {}), WebsterController)

    def test_rl_baseline_requires_checkpoint(self):
        args = SimpleNamespace(rl_checkpoint=None, rl_round=None,
                               rl_agent_conf=None, rl_device="auto", eightphase=False)
        for name in RL_BASELINES:
            with pytest.raises(ValueError, match="rl_checkpoint"):
                build_controller(name, args, {})

    def test_rl_registry_names(self):
        assert RL_MODEL_NAMES == {
            "colight": "Colight",
            "presslight": "PressLight",
            "mplight": "MPLight",
            "attendlight": "Attend",
            "advanceddqn": "AdvancedDQN",
            "citylight": "CityLight",
        }

    def test_import_baselines_does_not_pull_tensorflow_or_torch(self):
        code = (
            "import sys, baselines; "
            "assert 'tensorflow' not in sys.modules, 'baselines imported tensorflow'; "
            "assert 'torch' not in sys.modules, 'baselines imported torch'"
        )
        subprocess.run(
            [sys.executable, "-c", code], check=True, cwd=REPO_ROOT
        )
