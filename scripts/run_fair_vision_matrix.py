"""Run official Jev and three pinned open models through the same visual agent.

No network or simulation without --execute. All models receive the same camera
history, perception questions and phase policy; only image wire encoding differs.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_vlalight_jev import (build_cases, save_json, validate_summary,
    VISION_MODELS, check_image_api, check_open_image_model)
from scripts.experiments.preparation_cases import FLOWS
from jevlight.config import DATASETS
from jevlight.simulation_checkpoint import OutputLease

OFFICIAL = "jev-vision"
SHARED = dict(start_time=0, count=3600, duration=15, eightphase=False,
              fallback="previous", min_confidence=0.0, max_workers=8,
              jev_retries=3, jev_timeout=120.0, jev_min_interval=0.0,
              rolling_evaluation=True, hourly_interval=3600, visualize=False,
              use_wandb=False, packaging="per_intersection", speculative=False,
              cojev_history_steps=0, agent="jevlight", mock_jev=False)
METRICS = ("avg_waiting_time", "avg_queue_len", "avg_travel_time",
           "arrived_vehicle_count", "running_vehicle_count", "pending_vehicle_count")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    files = [ROOT / "run_jevlight.py", Path(__file__),
             ROOT / "scripts/benchmark_vlalight_jev.py", ROOT / "scripts/file_lock.py",
             ROOT / "config/vision_models.json"]
    for directory in ("jevlight", "utils"):
        files.extend((ROOT / directory).rglob("*.py"))
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(files))}


def endpoint_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Endpoints must be HTTP(S) URLs without credentials, queries or fragments")
    return value.rstrip("/")


def build_plan(open_models, endpoints=None, smoke=False):
    if len(open_models) != 3 or len(set(open_models)) != 3 or OFFICIAL in open_models:
        raise ValueError("Select exactly three distinct pinned vision models")
    for model in open_models:
        if model not in VISION_MODELS:
            raise ValueError("Open models must name the pinned config/vision_models.json entries")
    endpoints = dict(endpoints or {})
    if set(endpoints) - set(open_models):
        raise ValueError("Endpoint override does not name a selected open model")
    cases = {c["id"]: c for c in build_cases()}
    sources, jobs = source_hashes(), []
    for model in (OFFICIAL, *open_models):
        for flow, (dataset, _, traffic_file) in FLOWS.items():
            case = cases[f"{dataset}/{traffic_file.removesuffix('.rou.xml')}"]
            for seed in (1, 2, 3):
                path = ROOT / "config/jev-api" / f"jevlight_{flow}_s{seed}.json"
                config = json.loads(path.read_text(encoding="utf-8"))
                if any(config.get(k) != v for k, v in SHARED.items()):
                    raise ValueError(f"Shared experiment settings drifted: {path.relative_to(ROOT)}")
                if (config.get("dataset") != dataset or config.get("traffic_file") != traffic_file
                        or config.get("seed") != seed or config.get("dry_run", False)):
                    raise ValueError(f"Scenario, seed or policy mismatch: {path.relative_to(ROOT)}")
                if any("key" in name.lower() for name in config):
                    raise ValueError("Credentials must come from the environment or private vault")
                overrides = dict(image_decisions=True, image_agent="vlalight", image_renderer="vlalight",
                                 visual_cooperation=False, fail_on_image_fallback=True)
                if model == OFFICIAL:
                    if config["jev_transport"] != "official" or config["jev_base_url"] != "https://api.typesafe.ai":
                        raise ValueError("Official Jev must use the TypeSafe endpoint")
                    overrides.update(jev_model="jev-1.14.0")
                else:
                    overrides.update(jev_transport="local", jev_model=VISION_MODELS[model]["model_id"],
                                     jev_base_url="http://127.0.0.1:8123")
                if model in endpoints:
                    overrides["jev_base_url"] = endpoint_url(endpoints[model])
                endpoint_url(config["jev_base_url"])
                if smoke:
                    overrides["count"] = 30
                config.update(overrides)
                job = dict(id=f"{model}_{flow}_s{seed}", model=model, flow=flow, seed=seed,
                           config=path.relative_to(ROOT).as_posix(), config_sha256=digest(path),
                           effective_config=config, overrides=overrides,
                           input_mode="image", model_revision=None if model == OFFICIAL else VISION_MODELS[model]["revision"],
                           case=dict(case, horizon_s=config["count"],
                                     image_requests_per_seed=case["intersections"] * (config["count"] // 15)))
                jobs.append(job)
    return dict(protocol="upstream-3600s-15s-visual-v2", stage="smoke" if smoke else "formal",
                shared_settings={**SHARED, "count": 30 if smoke else 3600},
                open_models=list(open_models), source_hashes=sources, jobs=jobs,
                official_logical_evaluations=sum(j["case"]["image_requests_per_seed"] * 2
                                                 for j in jobs if j["model"] == OFFICIAL),
                cost_note="Logical evaluations exclude HTTP retries and credential rotation; no price estimate.")


def command_for(job, memo):
    command = [sys.executable, "-m", "run_jevlight", "--config", job["config"], "--memo", memo]
    for key, value in job["overrides"].items():
        if isinstance(value, bool):
            command.append(("--" if value else "--no-") + key)
        else:
            command.extend(["--" + key, str(value)])
    return command


def unchanged_inputs(job):
    dataset, directory, traffic_file = FLOWS[job["flow"]]
    return (digest(ROOT / job["config"]) == job["config_sha256"]
            and digest(ROOT / directory / traffic_file) == job["case"]["traffic_sha256"]
            and digest(ROOT / directory / DATASETS[dataset]["roadnet_file"]) == job["case"]["roadnet_sha256"])


def check_local_models(jobs):
    """Free health/identity checks before any official requests or SUMO runs."""
    import requests
    checked = set()
    for job in jobs:
        if job["model"] == OFFICIAL or job["model"] in checked:
            continue
        config = job["effective_config"]
        response = requests.get(config["jev_base_url"] + "/health", timeout=10)
        response.raise_for_status()
        identity = response.json()
        if (identity.get("model") != config["jev_model"] or
                identity.get("revision") != job["model_revision"]):
            raise ValueError(f"Wrong model at {config['jev_base_url']}; expected {config['jev_model']}")
        checked.add(job["model"])


def validate_run(job, summary_path):
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    config_path = summary_path.with_name("experiment_config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected = job["effective_config"]
    for key in (*SHARED, "seed", "dataset", "traffic_file", "jev_transport", "jev_model"):
        if config.get(key) != expected[key]:
            raise ValueError(f"Runtime configuration drifted: {key}")
    if summary.get("final/duration") != expected["count"]:
        raise ValueError("Incomplete simulation duration")
    if summary.get("mock_jev") or summary.get("dry_run") or summary.get("jev", {}).get("failures") != 0:
        raise ValueError("Mock, heuristic or failed model run is not a valid result")
    method = "jev-image" if job["model"] == OFFICIAL else job["model"]
    if (summary.get("image_agent") != "vlalight" or summary.get("visual_cooperation") is not False
            or validate_summary(summary, job["case"], job["seed"], method) != "complete"):
        raise ValueError("Visual model integrity check failed")
    for field in ("traffic_sha256", "roadnet_sha256"):
        if summary.get(field) != job["case"][field]:
            raise ValueError(f"Input data drifted: {field}")
    rows = 0
    trace_path = summary_path.with_name("jev_decisions.jsonl")
    with trace_path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("error") or row.get("fallback") not in (None, "empty_junction_local_ranking"):
                raise ValueError("Failed or fallback model decision")
            rows += 1
    if rows != job["case"]["image_requests_per_seed"]:
        raise ValueError("Incomplete per-intersection decision trace")
    values = {name: summary.get("final/" + name) for name in METRICS}
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values.values()):
        raise ValueError("Missing or nonfinite canonical metrics")
    return dict(values=values, artifacts={str(p): digest(p) for p in (summary_path, trace_path, config_path)})


def reusable(record):
    return record.get("status") == "complete" and bool(record.get("artifacts")) and all(
        Path(p).is_file() and digest(p) == value for p, value in record["artifacts"].items())


def write_scores(output, jobs):
    groups = {}
    for job in jobs:
        path = output / "completed" / (job["id"] + ".json")
        if not path.is_file():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("plan_sha256") != digest(output / "plan.json") or not reusable(record):
            continue
        groups.setdefault(job["model"] + "/" + job["flow"], []).append(record)
    scores = {}
    for key, records in groups.items():
        scores[key] = dict(seeds=[r["seed"] for r in records], metrics={
            name: dict(mean=statistics.mean(r["values"][name] for r in records),
                       sample_std=statistics.stdev(r["values"][name] for r in records) if len(records) > 1 else None)
            for name in METRICS})
    save_json(output / "scores.json", scores)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open-models", nargs=3, default=list(VISION_MODELS), metavar="VISION_MODEL")
    parser.add_argument("--endpoint", action="append", default=[], metavar="MODEL=URL")
    parser.add_argument("--models", nargs="+", help="Run a subset; official vision key is jev-vision")
    parser.add_argument("--flows", nargs="+", choices=tuple(FLOWS), default=list(FLOWS))
    parser.add_argument("--seeds", nargs="+", type=int, choices=(1, 2, 3), default=[1, 2, 3])
    parser.add_argument("--smoke", action="store_true", help="30-second checks, isolated from formal results")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Skip only hash-verified completed jobs")
    parser.add_argument("--limit", type=int, help="Maximum newly executed simulations")
    parser.add_argument("--output", type=Path, default=ROOT / "results/fair_vision_matrix")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        parser.error("limit must be positive")
    with ExitStack() as resources:
        try:
            endpoints = dict(item.split("=", 1) for item in args.endpoint)
            plan = build_plan(args.open_models, endpoints, args.smoke)
            selected_models = args.models or [OFFICIAL, *args.open_models]
            if set(selected_models) - {OFFICIAL, *args.open_models}:
                raise ValueError("Unknown selected model")
            output = args.output.resolve() / plan["stage"]
            if not output.is_relative_to(ROOT / "results"):
                raise ValueError("Output must be inside results/")
            output.mkdir(parents=True, exist_ok=True)
            if args.execute:
                resources.enter_context(OutputLease(output))
            path = output / "plan.json"
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != plan:
                raise ValueError("Existing plan has different code/config/data; choose a new --output")
            save_json(path, plan)
            selected = [j for j in plan["jobs"] if j["model"] in selected_models
                        and j["flow"] in args.flows and j["seed"] in args.seeds]
            print(f"Plan: {len(plan['jobs'])} conditions (4 x 7 x 3); selected {len(selected)}; {path}")
            print(f"Official logical evaluations for all 21 vision conditions: {plan['official_logical_evaluations']:,} (excludes retries)")
            if not args.execute:
                print("Plan only: no API calls, model downloads or SUMO runs.")
                return
            pending = []
            for job in selected:
                saved = output / "completed" / (job["id"] + ".json")
                existing = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else {}
                if existing and existing.get("plan_sha256") != digest(path):
                    raise ValueError("Completed record belongs to a different frozen plan")
                if existing and reusable(existing):
                    if not args.resume:
                        raise ValueError("Completed results exist; use --resume or a new --output")
                    print("Reusing " + job["id"])
                else:
                    pending.append(job)
            if args.limit:
                pending = pending[:args.limit]
            check_local_models(pending)
            checked = set()
            for job in pending:
                if job["model"] in checked:
                    continue
                if job["model"] == OFFICIAL:
                    error = check_image_api(output, image_agent="vlalight")
                else:
                    error = check_open_image_model(output, job["effective_config"]["jev_model"],
                        job["effective_config"]["jev_base_url"], retries=0, image_agent="vlalight")
                if error:
                    raise ValueError(f"Visual preflight failed: {job['model']}: {error}")
                checked.add(job["model"])
            for job in pending:
                if source_hashes() != plan["source_hashes"] or not unchanged_inputs(job):
                    raise ValueError("Code, configuration or traffic data changed after planning")
                attempt = output / "attempts" / (job["id"] + "_" + uuid.uuid4().hex)
                attempt.mkdir(parents=True)
                memo = "fair_" + attempt.name
                command = command_for(job, memo)
                record = dict(id=job["id"], model=job["model"], flow=job["flow"], seed=job["seed"],
                              status="running", plan_sha256=digest(path),
                              started_at=datetime.now(timezone.utc).isoformat(),
                              command=command, effective_config={**job["effective_config"], "memo": memo})
                save_json(attempt / "record.json", record)
                try:
                    print("Running " + job["id"], flush=True)
                    with (attempt / "runner.log").open("w", encoding="utf-8") as log:
                        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                    summaries = list((ROOT / "results/jev-api" / memo).glob("*/summary.json"))
                    if result.returncode or len(summaries) != 1:
                        raise ValueError(f"Runner exit={result.returncode}; summaries={len(summaries)}; see {attempt / 'runner.log'}")
                    record.update(validate_run(job, summaries[0]))
                    if source_hashes() != plan["source_hashes"] or not unchanged_inputs(job):
                        raise ValueError("Code, configuration or traffic data changed during the run")
                    record.update(status="complete", summary_path=str(summaries[0]))
                    completed = output / "completed" / (job["id"] + ".json")
                    completed.parent.mkdir(exist_ok=True)
                    save_json(completed, record)
                except BaseException as error:
                    record.update(status="failed", error=f"{type(error).__name__}: {error}")
                    raise
                finally:
                    save_json(attempt / "record.json", record)
                    write_scores(output, plan["jobs"])
        except (ValueError, OSError, RuntimeError) as error:
            parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
