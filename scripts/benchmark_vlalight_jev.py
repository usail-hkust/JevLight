"""Run the available SUMO scenarios with matched seeds and fixed horizons.

Planning is free. --execute runs the selected method; official Jev image calls
need an API key, while open-weight methods need their local model server.
Mock image runs are only smoke tests and never enter the score table.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jevlight.config import DATASETS
from scripts.fetch_vlalight_renderer import REVISION as RENDERER_REVISION

VISION_MODELS = json.loads((ROOT / "config/vision_models.json").read_text(encoding="utf-8"))
OPEN_VISION_MODELS = {key: value["model_id"] for key, value in VISION_MODELS.items()}
OPEN_VISION_BASE_URLS = dict.fromkeys(OPEN_VISION_MODELS, "http://127.0.0.1:8123")
BENCHMARK_TRAFFIC_FILES = {
    "jinan": {
        "anon_3_4_jinan_real.rou.xml",
        "anon_3_4_jinan_real_2000.rou.xml",
        "anon_3_4_jinan_real_2500.rou.xml",
    },
    "hangzhou": {
        "anon_4_4_hangzhou_real.rou.xml",
        "anon_4_4_hangzhou_real_5816.rou.xml",
    },
    "newyork": {
        "anon_28_7_newyork_real_double.rou.xml",
        "anon_28_7_newyork_real_triple.rou.xml",
    },
}


def save_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def check_image_api(output, retries=3, filename="api_preflight.json", image_agent="direct"):
    from PIL import Image
    from jevlight.jev_client import JevClient

    probe_dir = ROOT / "logs" / "benchmark_vlalight"
    probe_dir.mkdir(parents=True, exist_ok=True)
    if image_agent in ("vlalight", "vlalight-grouped"):
        labels = ("EASTBOUND", "WESTBOUND", "NORTHBOUND", "SOUTHBOUND")
        images = {}
        state = {"current_views": [], "previous_views": []}
        for frame_name, frame_color in (("current", "gray"), ("previous", "silver")):
            for label in labels:
                ref = f"api-preflight-{frame_name}-{label.lower()}"
                image = probe_dir / f"{ref}.jpg"
                Image.new("RGB", (384, 720), frame_color).save(image)
                state[f"{frame_name}_views"].append({"view": label, "image": ref})
                images[ref] = image
        question = {"probe": {"type": "choice",
                              "instructions": "Confirm the supplied labelled camera frame history is readable.",
                              "criteria": {"readable": "The labelled camera frames are present and readable.",
                                           "unreadable": "The camera frames are absent or unreadable."}}}
    else:
        image = probe_dir / "api_preflight.jpg"
        Image.new("RGB", (768, 1440), "gray").save(image)
        state = {"camera_image": "api-preflight"}
        images = {"api-preflight": image}
        question = {"probe": {"type": "choice", "instructions": "Read api-preflight; choose wait for an empty scene.",
                              "criteria": {"go": "Vehicles can proceed", "wait": "No visible traffic"}}}
    result = JevClient(transport="official", model="jev-1.14.0", max_retries=retries).evaluate(
        state, question, assets=images,
    )
    error = result.error
    answer = result.answers.get("probe")
    expected = {"readable", "unreadable"} if image_agent in ("vlalight", "vlalight-grouped") else {"go", "wait"}
    if not error and (result.model != "jev-1.14.0" or
                      not isinstance(answer, dict) or answer.get("choice") not in expected):
        error = "Image preflight returned an unexpected model or invalid choice"
    record = {"checked_at": datetime.now().astimezone().isoformat(),
              "status": "blocked_api" if error else "ready", "error": error,
              "model": result.model, "input_tokens": result.input_tokens,
              "output_tokens": result.output_tokens, "latency_s": result.latency}
    save_json(output / filename, record)
    return error


def check_open_image_model(output, model, base_url=None, retries=2, image_agent="direct"):
    from PIL import Image
    from jevlight.jev_client import JevClient

    probe_dir = ROOT / "logs" / "benchmark_vlalight"
    probe_dir.mkdir(parents=True, exist_ok=True)
    image = probe_dir / "open_model_preflight.jpg"
    Image.new("RGB", (768, 1440), "gray").save(image)
    state = {"camera_image": "open-model-preflight"}
    assets = {"open-model-preflight": image}
    questions = {"probe": {"type": "choice", "instructions": "Choose wait for an empty scene.",
                           "criteria": {"go": "Vehicles can proceed", "wait": "No visible traffic"}}}
    if image_agent != "direct":
        state, assets = {"current_views": [], "previous_views": []}, {}
        for frame in ("current", "previous"):
            for label in ("EASTBOUND", "WESTBOUND", "NORTHBOUND", "SOUTHBOUND"):
                ref = f"preflight-{frame}-{label}"
                path = probe_dir / f"{ref}.jpg"
                Image.new("RGB", (384, 720), "gray").save(path)
                state[frame + "_views"].append({"view": label, "image": ref})
                assets[ref] = path
        questions = {f"probe_{i}": dict(questions["probe"]) for i in range(24)}
    result = JevClient(transport="local", model=model, base_url=base_url,
                       max_retries=retries).evaluate(state, questions, assets=assets)
    error = result.error
    if error and ("ConnectionError" in error or "Max retries exceeded" in error):
        error = f"Could not connect to the local model server at {base_url or 'the configured endpoint'}."
    if not error and result.model != model:
        error = f"Open vision model mismatch: expected {model!r}, got {result.model!r}"
    if not error and any(not isinstance(result.answers.get(key), dict) or
                         result.answers[key].get("choice") not in {"go", "wait"} for key in questions):
        error = "Open vision model returned an invalid choice"
    record = {"checked_at": datetime.now().astimezone().isoformat(),
              "status": "blocked_local_model" if error else "ready", "error": error,
              "model": result.model, "requested_model": model,
              "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
              "latency_s": result.latency, "image_count": len(assets), "question_count": len(questions)}
    save_json(output / f"preflight_{model.rsplit('/', 1)[-1]}.json", record)
    return error


def build_cases():
    cases = []
    for dataset, config in DATASETS.items():
        data = ROOT / "data" / config["template"] / config["road_net"]
        if not (data / config["roadnet_file"]).is_file():
            continue
        for filename in config["traffic_files"]:
            if filename not in BENCHMARK_TRAFFIC_FILES.get(dataset, set()):
                continue
            path = data / filename
            if not path.is_file():
                continue
            # Match the upstream benchmark, including unfinished New York trips.
            horizon = 3600
            cases.append({
                "id": f"{dataset}/{path.name.removesuffix('.rou.xml')}",
                "dataset": dataset, "traffic_file": filename,
                "intersections": config["num_intersections"], "horizon_s": horizon,
                "traffic_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "roadnet_sha256": hashlib.sha256((data / config["roadnet_file"]).read_bytes()).hexdigest(),
                "image_requests_per_seed": config["num_intersections"] * math.ceil((horizon - 1) / 15),
            })
    return cases


def validate_summary(summary, case, seed, method, model=None):
    for field in ("dataset", "traffic_file", "traffic_sha256", "roadnet_sha256"):
        if summary.get(field) != case[field]:
            return "invalid_metadata"
    if summary.get("seed") != seed or summary.get("control_interval_s") != 15:
        return "invalid_metadata"
    if summary.get("final/end_time") != case["horizon_s"]:
        return "incomplete_horizon"
    if method == "maxpressure":
        return "complete" if (summary.get("dry_run") and
                              summary.get("agent_mode") == "maxpressure" and
                              not summary.get("image_decisions")) else "invalid_method"
    if not summary.get("image_decisions") or summary.get("image_renderer") != "vlalight":
        return "invalid_method"
    image_agent = summary.get("image_agent", "direct")
    if image_agent not in {"direct", "vlalight", "vlalight-grouped"}:
        return "invalid_method"
    if image_agent == 'vlalight-grouped' and case['dataset'] != 'jinan':
        return 'invalid_method'
    if image_agent in ('vlalight', 'vlalight-grouped'):
        from jevlight.visual_agent import VisualAgent, JinanGroupedVisualAgent
        agent = JinanGroupedVisualAgent if image_agent == 'vlalight-grouped' else VisualAgent
        expected = agent.prompt_version + ('-co' if summary.get('visual_cooperation') else '')
        if summary.get('visual_prompt_version') != expected:
            return 'invalid_method'
    if summary.get("renderer_metadata", {}).get("revision") != RENDERER_REVISION:
        return "invalid_method"
    expected_mock = method == "smoke"
    if method == "jev-image":
        if summary.get("jev_transport") != "official" or summary.get("jev_model") != "jev-1.14.0":
            return "invalid_method"
    elif method in OPEN_VISION_MODELS:
        if (summary.get("jev_transport") != "local" or
                summary.get("jev_model") != (model or OPEN_VISION_MODELS[method])):
            return "invalid_method"
    elif method == "smoke":
        if summary.get("jev_transport") != "official" or summary.get("jev_model") != "jev-1.14.0":
            return "invalid_method"
    else:
        return "invalid_method"
    if bool(summary.get("mock_jev")) != expected_mock:
        return "invalid_method"
    expected_requests = case["image_requests_per_seed"] * {
        'direct': 1, 'vlalight': 2, 'vlalight-grouped': 3}[image_agent]
    if summary.get("jev", {}).get("requests") != expected_requests:
        return "incomplete_requests"
    if summary.get("jev", {}).get("failures") != 0 or summary.get("fallback_count") != 0:
        return "degraded_fallbacks"
    return "smoke_only" if expected_mock else "complete"


def aggregate(runs):
    groups = {}
    for run in runs:
        if run["status"] == "complete":
            groups.setdefault(run["case"], []).append(run["summary"])
    result = {}
    for name, summaries in groups.items():
        fields = ("avg_travel_time", "avg_waiting_time", "avg_queue_len",
                  "arrived_vehicle_count", "running_vehicle_count", "pending_vehicle_count")
        result[name] = {"seeds": [s["seed"] for s in summaries]}
        for field in fields:
            values = [s[f"final/{field}"] for s in summaries]
            result[name][field] = {"mean": statistics.mean(values),
                                   "sample_std": statistics.stdev(values) if len(values) > 1 else None}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=("maxpressure", "jev-image", "smoke", *OPEN_VISION_MODELS), default="jev-image")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--datasets", nargs="+")
    parser.add_argument("--cases", nargs="+", help="Exact scenario IDs from the saved plan, e.g. jinan/anon_3_4_jinan_real")
    parser.add_argument("--output", type=Path, default=Path("results/vlalight_jev"))
    parser.add_argument("--workers", type=int, default=1, choices=(1, 2))
    parser.add_argument("--vlalight_root", default="logs/vlalight-source/VLALight")
    parser.add_argument("--jev_base_url", default=None,
                        help="Local image-capable System One endpoint (default port 8123)")
    parser.add_argument("--horizon", type=int, choices=(30, 3600), default=3600,
                        help="30-second real-model smoke or the formal 3600-second protocol")
    parser.add_argument("--image_agent", choices=("direct", "vlalight", "vlalight-grouped"), default="direct",
                        help="Direct image choice or two-stage VLALight-inspired visual agent")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--jev_retries", type=int, default=3)
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("seeds must be unique")
    if args.jev_retries < 0:
        parser.error("jev_retries must be nonnegative")
    if args.method != "maxpressure" and args.workers != 1:
        parser.error("image experiments run serially to bound GPU memory and API load")
    cases = build_cases()
    if args.datasets:
        available = {c["dataset"] for c in cases}
        if set(args.datasets) - available:
            parser.error(f"unavailable datasets: {set(args.datasets) - available}")
        cases = [c for c in cases if c["dataset"] in args.datasets]
    if args.cases:
        available = {c["id"] for c in cases}
        if set(args.cases) - available:
            parser.error(f"unavailable scenarios: {set(args.cases) - available}")
        cases = [c for c in cases if c["id"] in args.cases]
        if not cases:
            parser.error("no scenarios selected")
    if args.method == "smoke":
        # One short route per network is enough to exercise all camera batches.
        first = {}
        for case in cases:
            first.setdefault(case["dataset"], case)
        cases = [dict(c, horizon_s=30, image_requests_per_seed=c["intersections"] * 2)
                 for c in first.values()]
    elif args.horizon == 30:
        cases = [dict(c, horizon_s=30, image_requests_per_seed=c["intersections"] * 2) for c in cases]
    if args.image_agent == 'vlalight-grouped' and any(c['dataset'] != 'jinan' for c in cases):
        parser.error('vlalight-grouped requires --datasets jinan or an explicit Jinan case')
    request_multiplier = {'direct': 1, 'vlalight': 2, 'vlalight-grouped': 3}[args.image_agent]
    output_stem = (args.method if args.image_agent == "direct" or args.method == "maxpressure"
                   else f"{args.method}-{args.image_agent}")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    plan = {"method": args.method, "seeds": args.seeds, "control_interval_s": 15,
            "yellow_time_s": 5, "cases": cases,
            "model": OPEN_VISION_MODELS.get(args.method, "jev-1.14.0" if args.method in ("jev-image", "smoke") else None),
            "image_agent": args.image_agent,
            "jev_retries": args.jev_retries if args.method != "maxpressure" else 0,
            "estimated_image_requests": (sum(c["image_requests_per_seed"] for c in cases)
                                          * len(args.seeds) * request_multiplier),
            "protocol": "upstream fixed 3600 seconds; no clearance; original canonical metrics",
            "execute": args.execute}
    save_json(args.output / f"plan_{output_stem}.json", plan)
    print(f"{len(cases)} scenarios x {len(args.seeds)} seeds; image requests: {plan['estimated_image_requests']:,}", flush=True)
    if not args.execute:
        return
    if args.method == "jev-image" and not (os.getenv("TYPESAFE_API_KEY") or os.getenv("JEV_API_KEY")):
        parser.error("TypeSafe API credentials missing; plan saved, no paid calls made")
    if args.method == "jev-image":
        error = check_image_api(args.output, retries=args.jev_retries,
                                filename=f"api_preflight-{args.image_agent}.json",
                                image_agent=args.image_agent)
        if error:
            parser.error(f"Image API preflight failed; existing results preserved: {error}")
    elif args.method in OPEN_VISION_MODELS:
        open_base_url = (args.jev_base_url or
                         os.environ.get("JEV_OPEN_VISION_BASE_URL") or
                         OPEN_VISION_BASE_URLS[args.method])
        error = check_open_image_model(args.output, OPEN_VISION_MODELS[args.method],
                                       open_base_url, retries=args.jev_retries, image_agent=args.image_agent)
        if error:
            parser.error(f"Open vision model preflight failed; existing results preserved: {error}")

    def execute(item):
        case, seed = item
        memo = f"VLALightBenchmark/{args.method}"
        if args.method != "maxpressure":
            memo += f"/{args.image_agent}"
        memo += f"/{case['id']}/seed_{seed}"
        if case["horizon_s"] != 3600:
            memo += f"/smoke_{case['horizon_s']}s"
        legacy_dir = ROOT / "records" / memo
        if args.method == "maxpressure":
            memo = memo.replace("/", "_")
        model_name = OPEN_VISION_MODELS.get(args.method, "jev-1.14.0")
        model_name = ("maxpressure" if args.method == "maxpressure" else
                      "".join(c if c.isalnum() or c in "-_." else "_" for c in model_name))
        record_dir = ROOT / "results" / model_name / memo
        previous = sorted([*record_dir.glob("*/summary.json"), *legacy_dir.glob("*/summary.json")],
                          key=lambda p: p.stat().st_mtime)
        if args.resume:
            for path in reversed(previous):
                try:
                    summary = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    print(f"Ignoring unreadable summary: {path}", flush=True)
                    continue
                status = validate_summary(summary, case, seed, args.method)
                if status in {"complete", "smoke_only"}:
                    print(f"Reusing {case['id']} seed {seed}: {status}", flush=True)
                    return {"case": case["id"], "seed": seed, "status": status,
                            "summary_path": str(path.relative_to(ROOT)), "summary": summary}
        command = [sys.executable, "run_jevlight.py", "--dataset", case["dataset"],
                   "--traffic_file", case["traffic_file"], "--count", str(case["horizon_s"]),
                   "--seed", str(seed), "--start_time", "0", "--duration", "15",
                   "--no-eightphase", "--rolling_evaluation", "--hourly_interval", "3600",
                   "--no-visualize", "--no-use_wandb", "--agent", "jevlight",
                   "--packaging", "per_intersection", "--fallback", "previous",
                   "--min_confidence", "0.0", "--max_workers", "8",
                   "--jev_timeout", "120", "--jev_min_interval", "0.0",
                   "--cojev_history_steps", "0", "--speculative", "false", "--memo", memo]
        if args.method == "maxpressure":
            command += ["--dry_run"]
        elif args.method in OPEN_VISION_MODELS:
            command += ["--jev_transport", "local", "--image_decisions", "--image_renderer", "vlalight",
                        "--vlalight_root", args.vlalight_root,
                        "--jev_model", OPEN_VISION_MODELS[args.method],
                        "--jev_retries", str(args.jev_retries), "--fail_on_image_fallback"]
            command += ["--jev_base_url", open_base_url]
        else:
            command += ["--jev_transport", "official", "--image_decisions", "--image_renderer", "vlalight",
                        "--vlalight_root", args.vlalight_root, "--jev_model", "jev-1.14.0",
                        "--jev_retries", str(args.jev_retries),
                        "--fail_on_image_fallback"]
            if args.method == "smoke":
                command += ["--mock_jev"]
        if args.method != "maxpressure":
            command += ["--image_agent", args.image_agent]
            if args.image_agent in ("vlalight", "vlalight-grouped"):
                command += ["--visual_cooperation"]
        log_dir = ROOT / "logs" / "benchmark_vlalight" / args.method / args.image_agent / case["dataset"]
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        log = log_dir / f"{case['traffic_file']}.seed_{seed}.{stamp}.log"
        print(f"Running {args.method}: {case['id']} seed {seed}", flush=True)
        with log.open("w", encoding="utf-8") as output:
            completed = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        paths = sorted(record_dir.glob("*/summary.json"), key=lambda p: p.stat().st_mtime)
        result = {"case": case["id"], "seed": seed, "status": "failed", "log": str(log.relative_to(ROOT))}
        new_paths = [p for p in paths if p not in previous]
        if completed.returncode == 0 and new_paths:
            path = new_paths[-1]
            summary = json.loads(path.read_text(encoding="utf-8"))
            result.update(status=validate_summary(summary, case, seed, args.method),
                          summary_path=str(path.relative_to(ROOT)), summary=summary)
        print(f"{case['id']} seed {seed}: {result['status']}", flush=True)
        return result

    runs = []
    output_path = args.output / f"{output_stem}.json"
    items = [(c, seed) for c in cases for seed in args.seeds]
    if args.workers == 1:
        for item in items:
            result = execute(item)
            runs.append(result)
            save_json(output_path, {"plan": plan, "runs": runs, "aggregate": aggregate(runs)})
            if result["status"] not in {"complete", "smoke_only"}:
                raise SystemExit(1)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for result in pool.map(execute, items):
                runs.append(result)
                save_json(output_path, {"plan": plan, "runs": runs, "aggregate": aggregate(runs)})
    print(output_path)
    if any(r["status"] not in {"complete", "smoke_only"} for r in runs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
