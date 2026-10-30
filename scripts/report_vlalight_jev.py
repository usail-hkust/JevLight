"""Write the local benchmark report from validated, completed seed summaries."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.benchmark_vlalight_jev import OPEN_VISION_MODELS, aggregate, validate_summary

MODEL_LABELS = {
    "wemm-jev": "WeMM-JEV-27B (open weights)",
    "d3-turbo": "d3-turbo v1.1 (open weights)",
    "amos-1-large": "Amos 1 Large (open weights)",
}


def read_result(directory, method, image_agent="direct"):
    stem = method if image_agent == "direct" else f"{method}-{image_agent}"
    path = directory / f"{stem}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def checked_runs(result):
    if not result:
        return []
    cases = {case["id"]: case for case in result["plan"]["cases"]}
    runs = []
    for run in result["runs"]:
        status = "failed"
        if "summary" in run:
            status = validate_summary(run["summary"], cases[run["case"]],
                                      run["seed"], result["plan"]["method"],
                                      model=result["plan"].get("model"))
        runs.append({**run, "status": status})
    return runs


def score_table(result, plan):
    runs = checked_runs(result)
    scores = aggregate(runs)
    lines = ["| Scenario | Horizon (s) | Complete seeds | Travel (s) | Waiting (s) | Network queue |",
             "| --- | ---: | --- | ---: | ---: | ---: |"]
    for case in plan["cases"]:
        score = scores.get(case["id"])
        if not score:
            values, seeds = ["pending"] * 3, "0/" + str(len(plan["seeds"]))
        else:
            values = []
            for name in ("avg_travel_time", "avg_waiting_time", "avg_queue_len"):
                metric = score[name]
                values.append(f"{metric['mean']:.2f}" +
                              (f" ± {metric['sample_std']:.2f}" if metric["sample_std"] is not None else ""))
            seeds = f"{len(score['seeds'])}/{len(plan['seeds'])} ({','.join(map(str, score['seeds']))})"
        lines.append(f"| `{case['id']}` | {case['horizon_s']} | {seeds} | {' | '.join(values)} |")
    return "\n".join(lines)


def write_report(directory, image_agent="direct"):
    suffix = "" if image_agent == "direct" else f"-{image_agent}"
    baseline = read_result(directory, "maxpressure")
    methods = ["jev-image", *OPEN_VISION_MODELS]
    results = {method: read_result(directory, method, image_agent) for method in methods}
    plan = (results["jev-image"] or next((r for r in results.values() if r), None))
    official_plan_path = directory / f"plan_jev-image{'-' + image_agent if image_agent != 'direct' else ''}.json"
    if plan is None:
        plan_path = official_plan_path
        if not plan_path.exists():
            plan_path = next((directory / f"plan_{method}{suffix}.json" for method in OPEN_VISION_MODELS
                              if (directory / f"plan_{method}{suffix}.json").exists()), plan_path)
        if not plan_path.exists():
            raise FileNotFoundError("No Jev vision benchmark plan or result was found")
        plan = {"plan": json.loads(plan_path.read_text(encoding="utf-8"))}
    plan = plan["plan"]
    official_plan = results["jev-image"]["plan"] if results["jev-image"] else None
    if official_plan is None and official_plan_path.exists():
        official_plan = json.loads(official_plan_path.read_text(encoding="utf-8"))
    smoke = read_result(directory, "smoke", image_agent)
    baseline_runs = checked_runs(baseline)
    expected_baseline = (len(baseline["plan"]["cases"]) * len(baseline["plan"]["seeds"])) if baseline else 0
    baseline_count = sum(r["status"] == "complete" for r in baseline_runs)
    model_runs = {method: checked_runs(results[method]) for method in methods}
    model_counts = {}
    for method in methods:
        result = results[method]
        method_plan = result["plan"] if result else plan
        expected = len(method_plan["cases"]) * len(method_plan["seeds"])
        model_counts[method] = (sum(r["status"] == "complete" for r in model_runs[method]), expected)
    complete = expected_baseline > 0 and baseline_count == expected_baseline and all(
        count == expected for count, expected in model_counts.values())
    api_path = directory / f"api_preflight-{image_agent}.json"
    if image_agent == "direct" and not api_path.exists():
        api_path = directory / "api_preflight.json"
    api = json.loads(api_path.read_text(encoding="utf-8")) if api_path.exists() else None
    preflights = {"jev-image": api}
    for method in OPEN_VISION_MODELS:
        path = directory / f"preflight_{OPEN_VISION_MODELS[method].rsplit('/', 1)[-1]}.json"
        preflights[method] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    status = "complete" if complete else "in progress / incomplete"
    if not complete and api and api.get("status") == "blocked_api":
        status = "blocked: image API unavailable"
    summary_counts = ", ".join(
        f"{MODEL_LABELS.get(method, 'Official Jev 1.14.0')}: {count}/{expected}"
        for method, (count, expected) in model_counts.items())
    lines = ["# VLALight cameras + Jev: local evaluation", "",
             f"Selected image agent: `{image_agent}`.",
             "", f"Updated: {datetime.now().astimezone().isoformat(timespec='seconds')}", "",
             f"Status: **{status}**. "
             f"MaxPressure: **{baseline_count}/{expected_baseline}** completed seeds; "
             f"Vision models: {summary_counts}.", "",
             "A row with fewer than three seeds is preliminary. Pending cells are not model scores. "
             "Failed, fallback and mock runs are excluded. No conclusion about Jev improving over "
             "the baseline is supported until matched scenarios and seeds complete.", "",
             "## Protocol", "",
             "- Four supplied SUMO networks, ten route files, seeds 1/2/3; 15-second control "
             "interval and five seconds of yellow on a phase change.",
             "- Horizons cover the departure schedule, rounded up to five minutes, with a "
             "one-hour minimum. Jinan synthetic spans 24 hours; New York 28x7 spans 3,900 seconds. "
             "No clearance period is added; vehicles still travelling at the horizon are censored.",
             "- This repository's `MaxPressureController` maximizes incoming queued + approaching "
             "vehicle count. It does not subtract downstream pressure. It uses the same SUMO "
             "data, control timing and metric recorder as the Jev path, without rendering or API calls.",
             "- Vision methods use the same VLALight/TransSimHub/Panda3D camera, SUMO control "
             "interval and labelled 768x1440 composite. Direct mode sends one image and phase "
             "question per intersection. The vlalight agent sends four current and four previous "
             "labelled crops to typed perception, then routes estimates and observed lane relations "
             "to a separate phase decision. The experimental Jinan-only vlalight-grouped agent "
             "isolates movement lanes and uses two opposite-approach perception calls plus one "
             "phase call. Numeric simulator traffic measurements are excluded.",
             "- Means and sample standard deviations are over completed seeds. Travel time "
             "includes completed trips and elapsed time of active trips; it is not a completed-trip-only "
             "mean. Waiting is mean accumulated stopped time of observed vehicles. Network queue "
             "is the per-second total stopped queue averaged across time, not per intersection.",
             "- SUMO's existing teleport settings are retained. Teleports and unfinished vehicles "
             "are reported below because a low travel-time value alone can hide congestion. "
             "`min_expected` includes running and not-yet-inserted vehicles; do not add it to running.", "",
             "## Baseline results", "", score_table(baseline, baseline["plan"] if baseline else plan), ""]
    for method in methods:
        result = results[method]
        method_plan = result["plan"] if result else plan
        label = MODEL_LABELS.get(method, "Official Jev 1.14.0")
        lines.extend([f"## {label} results", "", score_table(result, method_plan), ""])
        preflight = preflights[method]
        if preflight:
            lines.extend([f"Image preflight: **{preflight['status']}**. "
                           f"{preflight.get('error') or 'The selected model returned a valid image decision.'}", ""])
    lines.extend([
             "## Traffic completion diagnostics", "",
             "Values are means over completed seeds; counts may therefore be fractional.", "",
             "| Method / scenario | Seeds | Arrived | Running | Min expected | Teleports |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"])
    diagnostic_runs = [("MaxPressure", baseline_runs, baseline["plan"] if baseline else plan)]
    diagnostic_runs.extend((MODEL_LABELS.get(method, "Official Jev 1.14.0"), model_runs[method],
                            results[method]["plan"] if results[method] else plan) for method in methods)
    for method, runs, method_plan in diagnostic_runs:
        for case in method_plan["cases"]:
            summaries = [r["summary"] for r in runs if r["case"] == case["id"] and r["status"] == "complete"]
            if summaries:
                values = [statistics.mean(s[field] for s in summaries) for field in
                          ("final/arrived_vehicle_count", "final/running_vehicle_count",
                           "final/pending_vehicle_count", "teleport_count")]
                lines.append(f"| {method} / `{case['id']}` | {len(summaries)} | " +
                             " | ".join(f"{value:.1f}" for value in values) + " |")
    if smoke:
        smoke_runs = checked_runs(smoke)
        requests = sum(r["summary"]["jev"]["requests"] for r in smoke_runs if r["status"] == "smoke_only")
        lines.extend(["", "## Pipeline verification", "",
                      f"{len(smoke_runs)} network checks, 30 seconds each, {requests} mock image "
                      "requests; these are plumbing checks and have no model score."])
    preflight = directory / "preflight.json"
    if preflight.exists():
        summary = json.loads(preflight.read_text(encoding="utf-8"))
        lines.append(f"A separate real 30-second Jinan preflight made {summary['jev']['requests']} "
                     f"requests, with {summary['jev']['failures']} failures and "
                     f"{summary['fallback_count']} fallback decisions. This short run is also excluded "
                     "from the full-horizon score tables.")
    jev_runs = model_runs["jev-image"]
    requests = sum(r["summary"]["jev"]["requests"] for r in jev_runs if r["status"] == "complete")
    tokens = sum(r["summary"]["jev"]["input_tokens"] for r in jev_runs if r["status"] == "complete")
    official_plan_text = (f"The official Jev plan has **{official_plan.get('estimated_image_requests', 0):,} "
                          "requests before retries. " if official_plan else
                          "No official Jev plan is saved. ")
    lines.extend(["", "## Usage and reproducibility", "",
                  official_plan_text +
                  f"Completed official Jev seeds currently report {requests:,} requests and {tokens:,} input tokens. "
                  "This excludes probes, failed/in-flight runs and any provider-side billing differences.", "",
                  "Official [model pricing](https://docs.typesafe.ai/models) at evaluation setup was "
                  "$0.042 per million input tokens, with free outputs; "
                  "[images](https://docs.typesafe.ai/images) count as input tokens. "
                  f"Completed-seed usage at that rate is approximately **${tokens * .042 / 1_000_000:.4f}**.", "",
                  "The first runs used Python 3.13.5, SUMO 1.24.0, Panda3D 1.10.16 and Pillow 12.2.0 "
                  "on Windows. Per-seed summaries embed simulator version, seed, wall time, "
                  "network/route SHA-256 hashes, Jev usage, renderer configuration and source revision. "
                  "Renderer assets are pinned to VLALight `9844f1b6bbd6b4fe80b481d3dd16fadce13c3b5d`. "
                  "Initial runs correctly record the pre-commit HEAD with `git_dirty: true`; "
                  "the local implementation commits preserve that working-tree implementation.", "",
                  ])
    plan_link = official_plan_path.name if official_plan and official_plan_path.exists() else next(
        (f"plan_{method}{suffix}.json" for method in OPEN_VISION_MODELS
         if (directory / f"plan_{method}{suffix}.json").exists()), None)
    if plan_link:
        lines.append(f"- [Benchmark plan]({plan_link})")
    for method, filename, label in (("maxpressure", "maxpressure.json", "Baseline seed summaries and aggregates"),
                                    ("smoke", f"smoke{'-' + image_agent if image_agent != 'direct' else ''}.json", "Mock camera checks")):
        if (directory / filename).exists():
            lines.append(f"- [{label}]({filename})")
    if results["jev-image"]:
        lines.append(f"- [Official Jev seed summaries and aggregates](jev-image{'-' + image_agent if image_agent != 'direct' else ''}.json)")
    for method in OPEN_VISION_MODELS:
        if results[method]:
            lines.append(f"- [{MODEL_LABELS[method]} seed summaries and aggregates]({method}{suffix}.json)")
    for method, preflight in preflights.items():
        if preflight:
            filename = (f"api_preflight-{image_agent}.json" if method == "jev-image" else
                        f"preflight_{OPEN_VISION_MODELS[method].rsplit('/', 1)[-1]}.json")
            lines.append(f"- [{MODEL_LABELS.get(method, 'Official Jev 1.14.0')} image preflight]({filename})")
    for recovery in sorted(directory.glob("recovery_*.json")):
        lines.extend(["", f"- [Interruption and recovery record]({recovery.name})"])
    lines.extend(["", "Detailed frames, decision traces, generated SUMO configurations and runtime "
                  "logs remain in ignored `records/` and `logs/` directories. Reproduce using the "
                  "commands in the root README. These measurements are separate from the old "
                  "CityFlow benchmark; no remote homepage or PR is updated.", ""])
    (directory / "README.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/vlalight_jev"))
    parser.add_argument("--image_agent", choices=("direct", "vlalight", "vlalight-grouped"), default="direct")
    args = parser.parse_args()
    write_report(args.output, args.image_agent)
