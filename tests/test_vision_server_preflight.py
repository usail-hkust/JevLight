from io import StringIO
from pathlib import Path
import builtins
import json
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_vision_server.sh"
PREFLIGHT = SCRIPT.read_text(encoding="utf-8").split(
    'python3 - "${MODELS[@]}" <<\'PY\'\n', 1)[1].split("\nPY\n", 1)[0]
MODEL_PREFLIGHT = SCRIPT.read_text(encoding="utf-8").split(
    '  "$RUNNER" - "$key" <<\'PY\'\n', 1)[1].split("\nPY\n", 1)[0]


def run_preflight(monkeypatch, tmp_path, selected, free_gib, cached=(), query_log=None):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/vision_models.json").write_text(json.dumps(
        {key: {} for key in ("wemm-jev", "d3-turbo", "amos-1-large")}))
    for key in cached:
        marker = tmp_path / ".local/vision-models" / key / "jevlight-download.json"
        marker.parent.mkdir(parents=True)
        marker.write_text("{}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["-", *selected])
    monkeypatch.setattr(shutil, "disk_usage", lambda _: SimpleNamespace(free=free_gib * 1024**3))
    def query(command, **kwargs):
        if query_log is not None:
            query_log.append(command)
        return "98304\n"
    monkeypatch.setattr(subprocess, "check_output", query)
    original_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda file, *a, **kw: (
        StringIO("MemTotal: 134217728 kB\n") if file == "/proc/meminfo"
        else original_open(file, *a, **kw)))
    exec(compile(PREFLIGHT, str(SCRIPT), "exec"), {})


def test_one_model_passes_without_reserving_three_checkpoints(monkeypatch, tmp_path):
    run_preflight(monkeypatch, tmp_path, ["wemm-jev"], 110)


def test_multigpu_node_checks_only_the_explicitly_selected_device(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2")
    calls = []
    run_preflight(monkeypatch, tmp_path, ["wemm-jev"], 110, query_log=calls)
    assert calls[0][-2:] == ["-i", "2"]


@pytest.mark.parametrize("devices", ["", "0,1"])
def test_gpu_selection_requires_exactly_one_device(monkeypatch, tmp_path, devices):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", devices)
    with pytest.raises(SystemExit, match="one GPU"):
        run_preflight(monkeypatch, tmp_path, ["wemm-jev"], 110)


def test_all_models_still_reserve_all_uncached_checkpoints(monkeypatch, tmp_path):
    monkeypatch.delenv("JEVLIGHT_RELEASE_COMPLETED_MODELS", raising=False)
    with pytest.raises(SystemExit, match="Need 235 GiB.*available 110.0 GiB"):
        run_preflight(monkeypatch, tmp_path, ["wemm-jev", "d3-turbo", "amos-1-large"], 110)


@pytest.mark.parametrize("cached", [(), ("wemm-jev",), ("d3-turbo",)])
def test_serial_startup_defers_checkpoint_space_to_each_model(monkeypatch, tmp_path, cached):
    monkeypatch.setenv("JEVLIGHT_RELEASE_COMPLETED_MODELS", "1")
    run_preflight(monkeypatch, tmp_path, ["wemm-jev", "d3-turbo", "amos-1-large"], 52.8, cached)


def test_serial_startup_still_requires_working_space(monkeypatch, tmp_path):
    monkeypatch.setenv("JEVLIGHT_RELEASE_COMPLETED_MODELS", "1")
    with pytest.raises(SystemExit, match="Need 40 GiB"):
        run_preflight(monkeypatch, tmp_path, ["wemm-jev", "d3-turbo", "amos-1-large"], 39)


@pytest.mark.parametrize("cached,free_gib,needed", [
    (True, 52.8, 40), (True, 39, 40), (False, 52.8, 105), (False, 110, 105)])
def test_each_model_reserves_its_own_download_space(monkeypatch, tmp_path, cached, free_gib, needed):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["-", "wemm-jev"])
    monkeypatch.setattr(shutil, "disk_usage", lambda _: SimpleNamespace(free=free_gib * 1024**3))
    if cached:
        marker = tmp_path / ".local/vision-models/wemm-jev/jevlight-download.json"
        marker.parent.mkdir(parents=True)
        marker.write_text("{}")
    if free_gib < needed:
        with pytest.raises(SystemExit, match=f"Need {needed} GiB free before preparing wemm-jev"):
            exec(compile(MODEL_PREFLIGHT, str(SCRIPT), "exec"), {})
    else:
        exec(compile(MODEL_PREFLIGHT, str(SCRIPT), "exec"), {})


def test_fifty_gib_is_insufficient_for_one_model(monkeypatch, tmp_path):
    with pytest.raises(SystemExit, match="Need 105 GiB.*available 50.0 GiB"):
        run_preflight(monkeypatch, tmp_path, ["wemm-jev"], 50)


@pytest.mark.parametrize("selected", [["typo"], ["wemm-jev", "wemm-jev"]])
def test_invalid_selection_fails_before_download(monkeypatch, tmp_path, selected):
    with pytest.raises(SystemExit, match="Select unique model keys"):
        run_preflight(monkeypatch, tmp_path, selected, 500)


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), (["--mode"], 2),
    (["--mode", "smoke"], 2), (["--models"], 2), (["--unknown"], 2)])
def test_cli_handles_help_and_invalid_arguments_before_setup(arguments, code):
    git_bash = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    bash = str(git_bash) if os.name == "nt" and git_bash.is_file() else shutil.which("bash")
    if not bash:
        pytest.skip("Bash is not installed")
    result = subprocess.run([bash, str(SCRIPT), *arguments], text=True, capture_output=True)
    assert result.returncode == code
    assert "Usage:" in result.stdout + result.stderr


def test_formal_entry_has_no_forced_smoke_simulation():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--smoke" not in text
    assert "--execute --resume --output results/vision_server" in text


def test_bootstrap_resolves_sumo_from_runner_environment(tmp_path):
    git_bash = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    bash = str(git_bash) if os.name == "nt" and git_bash.is_file() else shutil.which("bash")
    if not bash:
        pytest.skip("Bash is not installed")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    runner_bin = tmp_path / ".local/vision-runner/bin"
    runner_bin.mkdir(parents=True)
    sumo = runner_bin / "sumo"
    sumo.write_text('#!/usr/bin/env bash\nprintf "runner SUMO 1.24.0\\n"\n', encoding="utf-8")
    sumo.chmod(0o755)
    prefix = SCRIPT.read_text(encoding="utf-8").split('# Check before downloading', 1)[0]
    probe = scripts / SCRIPT.name
    probe.write_text(prefix + "sumo --version\n", encoding="utf-8")
    result = subprocess.run([bash, str(probe)], cwd=tmp_path.parent,
                            env={**os.environ, "JEVLIGHT_VISION_LOCK_FD": "1"},
                            text=True, capture_output=True, check=True)
    assert result.stdout.strip() == "runner SUMO 1.24.0"
