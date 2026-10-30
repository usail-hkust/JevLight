import json
from pathlib import Path

import pytest

from scripts import vision_server_storage as storage


KEY = "wemm-jev"


@pytest.fixture
def finished(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    plan = {"jobs": [{"id": f"{KEY}_flow{flow}_s{seed}", "model": KEY}
                     for flow in range(7) for seed in (1, 2, 3)]}
    monkeypatch.setattr(storage, "build_plan", lambda models: plan)
    output = tmp_path / "results/vision_server/formal"
    (output / "completed").mkdir(parents=True)
    (output / "plan.json").write_text(json.dumps(plan))
    artifact = output / "summary-fixture.json"
    artifact.write_text('{"fixture": true}')
    for job in plan["jobs"]:
        record = {**job, "status": "complete", "plan_sha256": storage.digest(output / "plan.json"),
                  "artifacts": {str(artifact): storage.digest(artifact)}}
        (output / "completed" / (job["id"] + ".json")).write_text(json.dumps(record))
    weights = tmp_path / ".local/vision-models" / KEY
    environment = tmp_path / (".local/vision-" + KEY)
    runner = tmp_path / ".local/vision-runner"
    for path in (weights, environment, runner):
        path.mkdir(parents=True)
        (path / "keep-or-delete.txt").write_text("fixture")
    (weights / "jevlight-download.json").write_text(json.dumps(
        {name: storage.VISION_MODELS[KEY][name] for name in ("model_id", "revision")}))
    return output, weights, environment, runner


def test_release_keeps_results_and_shared_runner(finished):
    output, weights, environment, runner = finished
    before = {str(p): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    assert storage.completed(KEY)
    storage.release(KEY)
    assert not weights.exists() and not environment.exists()
    assert (runner / "keep-or-delete.txt").is_file()
    assert before == {str(p): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    storage.release(KEY)  # An interrupted cleanup can safely run again.


def test_incomplete_model_is_not_deleted(finished):
    output, weights, environment, _ = finished
    next((output / "completed").glob("*.json")).unlink()
    assert not storage.completed(KEY)
    with pytest.raises(ValueError, match="before all 21"):
        storage.release(KEY)
    assert weights.is_dir() and environment.is_dir()


def test_corrupted_artifact_is_not_reused_or_deleted(finished):
    output, weights, environment, _ = finished
    (output / "summary-fixture.json").write_text("changed")
    assert not storage.completed(KEY)
    with pytest.raises(ValueError, match="before all 21"):
        storage.release(KEY)
    assert weights.is_dir() and environment.is_dir()


def test_different_model_identity_is_not_deleted(finished):
    _, weights, environment, _ = finished
    (weights / "jevlight-download.json").write_text('{"model_id": "other", "revision": "other"}')
    with pytest.raises(ValueError, match="different model/revision"):
        storage.release(KEY)
    assert weights.is_dir() and environment.is_dir()


def test_changed_plan_is_not_reused_or_deleted(monkeypatch, finished):
    _, weights, environment, _ = finished
    monkeypatch.setattr(storage, "build_plan", lambda models: {"changed": True})
    with pytest.raises(ValueError, match="different code/config/data"):
        storage.release(KEY)
    assert weights.is_dir() and environment.is_dir()


def test_resolved_path_outside_managed_directory_is_not_deleted(monkeypatch, finished, tmp_path):
    _, weights, environment, _ = finished
    resolve = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda p, *a, **kw: (
        tmp_path / "outside" if p == weights else resolve(p, *a, **kw)))
    with pytest.raises(ValueError, match="outside managed"):
        storage.release(KEY)
    assert weights.is_dir() and environment.is_dir()
