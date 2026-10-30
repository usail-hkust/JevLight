from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_jevlight
from baselines.run_baseline import build_configs as baseline_configs, parse_args as baseline_args
from jevlight.config import setup_dataset_config
from scripts import run_fair_vision_matrix as matrix


@pytest.fixture(scope="module")
def plan():
    return matrix.build_plan(list(matrix.VISION_MODELS))


def test_all_84_conditions_share_the_upstream_baseline_environment(plan):
    assert len(plan["jobs"]) == len({j["id"] for j in plan["jobs"]}) == 84
    assert plan["official_logical_evaluations"] == 662400
    for job in plan["jobs"]:
        command = matrix.command_for(job, "test")
        args = run_jevlight.parse_args(command[3:])
        for key, expected in matrix.SHARED.items():
            assert getattr(args, key) == expected, (job["id"], key)
        dataset = setup_dataset_config(args.dataset)
        _, actual, _ = run_jevlight.build_configs(args, dataset, "run")
        base = baseline_args(["--baseline", "maxpressure", "--dataset", args.dataset,
                              "--traffic_file", args.traffic_file, "--seed", str(args.seed),
                              "--proj_name", args.proj_name])
        _, expected, _ = baseline_configs(base, dataset, "run")
        for key in ("MODEL", "MODEL_NAME"):
            actual.pop(key)
            expected.pop(key)
        assert actual == expected, job["id"]
    for model in (matrix.OFFICIAL, *plan["open_models"]):
        assert len([j for j in plan["jobs"] if j["model"] == model]) == 21


def test_plan_mode_never_starts_a_process_or_sends_a_request(plan, monkeypatch, tmp_path):
    import requests
    monkeypatch.setattr(matrix, "ROOT", tmp_path)
    monkeypatch.setattr(matrix, "build_plan", lambda *args: plan)
    monkeypatch.setattr(matrix.subprocess, "run", lambda *a, **kw: pytest.fail("child started in plan mode"))
    monkeypatch.setattr(requests.sessions.Session, "request", lambda *a, **kw: pytest.fail("network used in plan mode"))
    output = tmp_path / "results/matrix"
    matrix.main(["--open-models", *plan["open_models"], "--output", str(output)])
    saved = json.loads((output / "formal/plan.json").read_text())
    assert len(saved["jobs"]) == 84
    assert not (output / "formal/attempts").exists()


def test_smoke_is_separate_and_never_claims_to_be_a_formal_result():
    plan = matrix.build_plan(list(matrix.VISION_MODELS), smoke=True)
    assert plan["stage"] == "smoke"
    assert plan["official_logical_evaluations"] == 5520
    assert {j["effective_config"]["count"] for j in plan["jobs"]} == {30}


def test_configuration_drift_is_rejected_before_any_run(monkeypatch):
    original = Path.read_text

    def drift(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path.as_posix().endswith("config/jev-api/jevlight_newyork-1_s1.json"):
            config = json.loads(value)
            config["count"] = 3900
            return json.dumps(config)
        return value

    monkeypatch.setattr(Path, "read_text", drift)
    with pytest.raises(ValueError, match="settings drifted"):
        matrix.build_plan(list(matrix.VISION_MODELS))


@pytest.mark.parametrize("models", [["clef-flash"] * 3, ["../escape", "clef-27b", "open-jev-9b"]])
def test_ambiguous_or_unsafe_model_selections_are_rejected(models):
    with pytest.raises(ValueError):
        matrix.build_plan(models)


def test_endpoint_cannot_embed_credentials():
    with pytest.raises(ValueError, match="credentials"):
        matrix.endpoint_url("https://secret@example.test/")


def test_wrong_local_model_blocks_before_any_official_job(plan, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"model": "wrong-checkpoint"}))
    with pytest.raises(ValueError, match="Wrong model"):
        matrix.check_local_models(plan["jobs"])


def test_resume_requires_unchanged_evidence(tmp_path):
    path = tmp_path / "summary.json"
    path.write_text("original")
    record = dict(status="complete", artifacts={str(path): matrix.digest(path)})
    assert matrix.reusable(record)
    path.write_text("changed")
    assert not matrix.reusable(record)
    assert not matrix.reusable(dict(status="complete", artifacts={}))


def test_execution_takes_a_lock_before_network_or_subprocesses(plan, monkeypatch, tmp_path):
    from contextlib import contextmanager
    import requests

    @contextmanager
    def already_owned(output):
        raise RuntimeError("already owned")
        yield

    monkeypatch.setattr(matrix, "ROOT", tmp_path)
    monkeypatch.setattr(matrix, "build_plan", lambda *a: plan)
    monkeypatch.setattr(matrix, "OutputLease", already_owned)
    monkeypatch.setattr(matrix.subprocess, "run", lambda *a, **kw: pytest.fail("duplicate simulation"))
    monkeypatch.setattr(requests, "get", lambda *a, **kw: pytest.fail("network before ownership"))
    with pytest.raises(SystemExit) as error:
        matrix.main(["--open-models", *plan["open_models"], "--execute",
                     "--output", str(tmp_path / "results/matrix")])
    assert error.value.code == 1


def test_failed_child_stops_before_a_second_paid_simulation(plan, monkeypatch, tmp_path):
    plan = deepcopy(plan)
    root = matrix.ROOT
    job = plan["jobs"][0]
    target = tmp_path / job["config"]
    target.parent.mkdir(parents=True)
    target.write_bytes((root / job["config"]).read_bytes())
    monkeypatch.setattr(matrix, "ROOT", tmp_path)
    monkeypatch.setattr(matrix, "build_plan", lambda *a: plan)
    monkeypatch.setattr(matrix, "source_hashes", lambda: plan["source_hashes"])
    monkeypatch.setattr(matrix, "unchanged_inputs", lambda job: True)
    monkeypatch.setattr(matrix, "check_image_api", lambda *a, **kw: None)
    commands = []

    def fail(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(matrix.subprocess, "run", fail)
    with pytest.raises(SystemExit) as error:
        matrix.main(["--open-models", *plan["open_models"], "--models", matrix.OFFICIAL,
                     "--execute", "--output", str(tmp_path / "results/test")])
    assert error.value.code == 1
    assert len(commands) == 1
    records = list((tmp_path / "results/test/formal/attempts").glob("*/record.json"))
    assert len(records) == 1
    assert json.loads(records[0].read_text())["status"] == "failed"


@pytest.mark.parametrize("all_complete", [False, True])
def test_resume_skips_verified_seeds_and_only_runs_unfinished(plan, monkeypatch, tmp_path, all_complete):
    plan = deepcopy(plan)
    monkeypatch.setattr(matrix, "ROOT", tmp_path)
    monkeypatch.setattr(matrix, "build_plan", lambda *a: plan)
    monkeypatch.setattr(matrix, "source_hashes", lambda: plan["source_hashes"])
    monkeypatch.setattr(matrix, "unchanged_inputs", lambda job: True)
    output = tmp_path / "results/test/formal"
    (output / "completed").mkdir(parents=True)
    matrix.save_json(output / "plan.json", plan)
    artifact = output / "summary-fixture.json"
    artifact.write_text("unchanged")
    jobs = [j for j in plan["jobs"] if j["model"] == "wemm-jev" and j["flow"] == "jinan-1"]
    for job in jobs if all_complete else jobs[:1]:
        matrix.save_json(output / "completed" / (job["id"] + ".json"),
            dict(id=job["id"], model=job["model"], flow=job["flow"], seed=job["seed"],
                 status="complete", plan_sha256=matrix.digest(output / "plan.json"),
                 artifacts={str(artifact): matrix.digest(artifact)},
                 values={key: 0 for key in matrix.METRICS}))
    checks, commands = [], []
    monkeypatch.setattr(matrix, "check_local_models", lambda pending: checks.append([j["id"] for j in pending]))
    monkeypatch.setattr(matrix, "check_open_image_model", lambda *a, **kw: pytest.fail("preflight for a complete model") if all_complete else None)

    def unfinished(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(matrix.subprocess, "run", unfinished)
    args = ["--models", "wemm-jev", "--flows", "jinan-1", "--execute", "--resume",
            "--output", str(output.parent)]
    if all_complete:
        matrix.main(args)
        assert commands == [] and checks == [[]]
    else:
        with pytest.raises(SystemExit):
            matrix.main(args)
        assert checks == [[job["id"] for job in jobs[1:]]]
        assert len(commands) == 1
        assert "config/jev-api/jevlight_jinan-1_s2.json" in commands[0]
        assert json.loads((output / "completed/wemm-jev_jinan-1_s1.json").read_text())["status"] == "complete"
