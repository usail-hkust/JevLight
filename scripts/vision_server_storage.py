"""Release only managed model files after all 21 conditions pass validation."""
from pathlib import Path
import json
import shutil

from scripts.run_fair_vision_matrix import build_plan, digest, reusable, VISION_MODELS

ROOT = Path(__file__).resolve().parents[1]


def completed(key):
    if key not in VISION_MODELS:
        raise ValueError(f"Unknown model: {key}")
    output = ROOT / "results/vision_server/formal"
    path = output / "plan.json"
    if not path.is_file():
        return False
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan != build_plan(list(VISION_MODELS)):
        raise ValueError("Existing results have different code/config/data; refusing reuse or cleanup")
    jobs = [job for job in plan["jobs"] if job["model"] == key]
    if len(jobs) != 21:
        raise ValueError("Expected seven flows and three seeds before model cleanup")
    plan_hash = digest(path)
    for job in jobs:
        path = output / "completed" / (job["id"] + ".json")
        if not path.is_file():
            return False
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("id") != job["id"] or record.get("model") != key or
                record.get("plan_sha256") != plan_hash or not reusable(record)):
            return False
    return True


def release(key):
    if not completed(key):
        raise ValueError(f"Refusing cleanup before all 21 conditions complete: {key}")
    local = ROOT / ".local"
    weights = local / "vision-models" / key
    environment = local / ("vision-" + key)
    targets = (weights, environment)
    for path in targets:
        if path.is_symlink() or not path.resolve().is_relative_to(local.resolve()):
            raise ValueError(f"Refusing cleanup outside managed model directories: {path}")
        if path.exists() and not path.is_dir():
            raise ValueError(f"Expected a managed directory: {path}")
    if weights.exists():
        identity = json.loads((weights / "jevlight-download.json").read_text(encoding="utf-8"))
        spec = VISION_MODELS[key]
        if identity != {name: spec[name] for name in ("model_id", "revision")}:
            raise ValueError("Refusing cleanup of weights with a different model/revision")
    for path in targets:
        if path.exists():
            shutil.rmtree(path)
