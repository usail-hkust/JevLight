"""Collect per-run serving telemetry for the composite index and cost plane.

The published benchmark matrix (``assets/benchmark.json``) only carries the
three traffic metrics.  The index page also plots *what a task costs to run*,
so this script reads each published run's decision log and records the serving
side of the task: how many decisions were taken, how long the model was busy,
how many input tokens it consumed and how long the whole run took.

Runs are located in two ways:

* completed experiment records and the legacy archive know their own summary
  path, so their decision log is found directly;
* published aggregate groups that this checkout has no record for (their
  numbers came from an earlier machine) are recovered from ``--results-root``:
  the ``<model>/<mode>_<flow>_s<seed>`` run directories whose summary metrics
  reproduce the published mean and standard deviation.

Only aggregate numbers leave the run directory: no prompts, states or answers
are stored.

Usage::

    python scripts/benchmark/collect_telemetry.py \
        --records results/experiments/records \
        --legacy-csv results/decision_models/2a800/experiment_records.csv \
        --benchmark assets/benchmark.json --results-root results \
        --out assets/telemetry.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import itertools
import json
import math
import os
import sys
from pathlib import Path

METRICS = ('att', 'awt', 'aql')
SUMMARY_KEYS = {
    'att': 'final/avg_travel_time',
    'awt': 'final/avg_waiting_time',
    'aql': 'final/avg_queue_len',
}


def step_serving(path: Path) -> dict | None:
    """Walk a decision log: steps, decisions, tokens, fallbacks, busy seconds.

    One control step issues its requests together, so the step waits for its
    slowest request: the step's serving time is that maximum.  Summing the
    maxima measures time the model actually spent answering, with simulator
    time excluded.
    """
    steps: dict[int, float] = {}
    decisions = fallbacks = tokens = 0
    try:
        stream = path.open('r', encoding='utf-8', errors='replace')
    except OSError:
        return None
    with stream:
        for line in stream:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            step = record.get('step')
            if step is None:
                continue
            step = int(step)
            steps.setdefault(step, 0.0)
            latency = record.get('request_latency')
            if latency is not None:
                latency = float(latency)
                if latency > steps[step]:
                    steps[step] = latency
            if record.get('question_id'):
                decisions += 1
                tokens += int(record.get('request_input_tokens') or 0)
            if record.get('fallback'):
                fallbacks += 1
    return dict(steps=len(steps), decisions=decisions, fallbacks=fallbacks,
                tokens_in=tokens, serving_s=round(sum(steps.values()), 3))


def gpu_count(value) -> int | None:
    text = str(value or '').strip()
    if text == '':
        return None
    if text == 'None':
        return 1
    if text.startswith('GPU-'):
        return 1
    return max(1, len([part for part in text.split(',') if part.strip()]))


def write_run(*, model, mode, flow, seed, source, wall_s,
              gpu_value, batch_size, log_path, extra: dict | None = None) -> dict | None:
    if not log_path or not Path(log_path).is_file():
        return None
    stats = step_serving(Path(log_path))
    if stats is None:
        return None
    entry = dict(id=f'{model}_{mode}_{flow}_s{seed}', model=model, mode=mode,
                 flow=flow, seed=int(seed), source=source,
                 wall_s=round(float(wall_s), 3) if wall_s is not None else None,
                 gpus=gpu_count(gpu_value),
                 batch_size=batch_size if batch_size not in (None, 0) else None,
                 **stats)
    if extra:
        entry.update(extra)
    return entry


def read_summary_metrics(path: Path) -> dict | None:
    try:
        summary = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    values = {}
    for key, field in SUMMARY_KEYS.items():
        value = summary.get(field)
        if value is None:
            return None
        values[key] = float(value)
    return values


def recover_group(results_root: Path, model: str, mode: str, flow: str,
                  published: dict) -> list | None:
    """Find the three runs behind a published aggregate by metric fingerprint.

    Run directories are usually named ``<mode>_<flow>_s<seed>`` but earlier
    campaigns prefixed the machine (``a40_transfer_a800_cojevlight_...``), so
    the directory match is on the suffix, not on the whole name.
    """
    candidates = {}
    for seed in (1, 2, 3):
        suffix = f'{mode}_{flow}_s{seed}'
        pattern = results_root / model / f'*{suffix}' / '*' / 'summary.json'
        found = []
        for path in glob.glob(str(pattern)):
            if Path(path).parent.parent.name.endswith(suffix):
                values = read_summary_metrics(Path(path))
                if values:
                    found.append((Path(path).parent, values))
        candidates[seed] = found

    if any(not found for found in candidates.values()):
        return None

    def close(a: float, b: float) -> bool:
        return abs(a - b) <= 1e-6 * max(1.0, abs(b))

    for combo in itertools.product(candidates[1], candidates[2], candidates[3]):
        means = {m: sum(c[1][m] for c in combo) / 3 for m in METRICS}
        if not all(close(means[m], published[m]['mean']) for m in METRICS):
            continue
        sds = {}
        for m in METRICS:
            values = [c[1][m] for c in combo]
            sds[m] = math.sqrt(sum((v - means[m]) ** 2 for v in values) / (len(values) - 1))
        target = published['att'].get('sd')
        if target is not None and not close(sds['att'], target):
            continue
        return [dict(directory=combo[i][0], seed=i + 1) for i in range(3)]
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--records', default='results/experiments/records')
    parser.add_argument('--legacy-csv',
                        default='results/decision_models/2a800/experiment_records.csv')
    parser.add_argument('--benchmark', default='assets/benchmark.json')
    parser.add_argument('--results-root', default='results')
    parser.add_argument('--out', default='assets/telemetry.json')
    args = parser.parse_args()

    bench = json.loads(Path(args.benchmark).read_text(encoding='utf-8'))
    runs: list = []
    seen: set[tuple] = set()
    notes = dict(records=0, legacy=0, recovered=0, unrecovered=[])

    def remember(entry):
        if entry is None:
            return
        key = (entry['model'], entry['mode'], entry['flow'], entry['seed'])
        if key in seen:
            return
        seen.add(key)
        runs.append(entry)

    for path in sorted(glob.glob(os.path.join(args.records, '*.json'))):
        try:
            record = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if record.get('status') != 'completed':
            continue
        summary_path = record.get('summary_path')
        remember(write_run(
            model=record['model_key'], mode=record['mode'],
            flow=record['traffic_id'], seed=record['seed'], source='record',
            wall_s=record.get('wall_duration_s'),
            gpu_value=record.get('gpu_uuid', record.get('gpu')),
            batch_size=record.get('pilot_batch_size'),
            log_path=Path(os.path.dirname(summary_path)) / 'jev_decisions.jsonl'
            if summary_path else None))

    if os.path.isfile(args.legacy_csv):
        with open(args.legacy_csv, encoding='utf-8') as stream:
            for row in csv.DictReader(stream):
                if row.get('status') != 'completed':
                    continue
                summary_path = row.get('summary_path')
                remember(write_run(
                    model=row['model_key'], mode=row['mode'],
                    flow=row['traffic_id'], seed=row['seed'], source='legacy',
                    wall_s=None, gpu_value=row.get('gpu'), batch_size=None,
                    log_path=Path(os.path.dirname(summary_path)) / 'jev_decisions.jsonl'
                    if summary_path else None))

    # Published groups with no record in this checkout: recover from disk.
    root = Path(args.results_root)
    known_gpus: dict[str, int] = {}
    for run in runs:
        if run['gpus']:
            known_gpus[run['model']] = max(known_gpus.get(run['model'], 1), run['gpus'])
    groups: dict[tuple, dict] = {}
    for entry in bench['aggregates']:
        groups.setdefault((entry['model'], entry['mode']), {})[entry['flow']] = entry['metrics']
    for (model, mode), by_flow in groups.items():
        if mode == 'maxpressure':
            continue
        for flow, published in by_flow.items():
            if any(k[:3] == (model, mode, flow) for k in seen):
                continue
            found = recover_group(root, model, mode, flow, published) if root.is_dir() else None
            if not found:
                continue
            notes['recovered'] += 1
            for run in found:
                directory = run['directory']
                batch = wall = None
                metadata = directory / 'run_metadata.json'
                if metadata.is_file():
                    try:
                        record = json.loads(metadata.read_text(encoding='utf-8'))
                    except (OSError, ValueError):
                        record = {}
                    batch = record.get('batch_size')
                    wall = record.get('wall_duration_s')
                hosted = model == 'jev-api'
                remember(write_run(
                    model=model, mode=mode, flow=flow, seed=run['seed'],
                    source='recovered', wall_s=wall,
                    gpu_value=0 if hosted else known_gpus.get(model, 1),
                    batch_size=batch,
                    log_path=directory / 'jev_decisions.jsonl',
                    extra=dict(hosted=True) if hosted else None))

    runs.sort(key=lambda r: (r['model'], r['mode'], r['flow'], r['seed']))
    covered = {(r['model'], r['mode'], r['flow']) for r in runs}
    notes['unrecovered'] = sorted(f'{m}|{mode}|{flow}' for (m, mode), by_flow in groups.items()
                                  for flow in by_flow if (m, mode, flow) not in covered)
    payload = dict(
        schema_version=1,
        description='Per-run serving telemetry behind the composite index and cost plane.',
        semantics=dict(
            serving_s='Sum over control steps of the slowest request latency in that step; '
                      'time the model spent answering one task, simulator excluded.',
            wall_s='Wall duration of the recorded run, simulator included.',
            gpus='GPUs held by the run; tensor-parallel runs count every card, hosted '
                 'API runs own none.',
            tokens_in='Input tokens summed over model decisions in the run.',
            decisions='Model decisions in the run; empty junctions never call the model.',
        ),
        runs=runs,
        totals=dict(runs=len(runs), recovered=notes['recovered'],
                    unrecovered=len(notes['unrecovered'])),
        notes=notes,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f"{len(runs)} runs ({notes['recovered']} recovered, "
          f"{len(notes['unrecovered'])} groups without a log) -> {out}", file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
