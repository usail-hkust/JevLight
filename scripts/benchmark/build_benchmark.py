"""Rebuild assets/benchmark.json from the formal experiment records.

Published rows keep their existing shape: one entry per (model, flow, mode) with
the arithmetic mean and sample standard deviation of the three seeds, plus the
per-seed runs the page can cite.
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / 'results/experiments/records'
LEGACY_CSV = ROOT / 'results/decision_models/2a800/experiment_records.csv'
BENCHMARK = ROOT / 'assets/benchmark.json'
BASELINES = ROOT / 'assets/baselines.json'

METRICS = ('att', 'awt', 'aql')


def display_names() -> dict:
    """Model id -> human name, derived from the ids already published."""
    existing = json.loads(BENCHMARK.read_text()) if BENCHMARK.is_file() else {}
    names = {m['id']: m['name'] for m in existing.get('models', [])}
    return names


# Display names that the id alone cannot produce faithfully.
NAME_OVERRIDES = {
    'kev-27b': 'Kev 27B',
    'startlux-0.8b': 'StartLux 0.8B',
    'startlux-2b': 'StartLux 2B',
    'startlux-4b': 'StartLux 4B',
    'startlux-9b': 'StartLux 9B',
    'startlux-27b': 'StartLux 27B',
}


def default_name(identifier: str) -> str:
    """startlux-0.8b -> StartLux 0.8B, pplx-decider-v1.2 -> PPLX Decider v1.2."""
    parts = identifier.split('-')
    out = []
    for part in parts:
        low = part.lower()
        if low == 'pplx':
            out.append('PPLX')
        elif low in ('jev', 'd3', 'clef', 'kev', 'aql', 'att', 'awt'):
            out.append(low.upper() if low != 'clef' else 'Clef')
        elif low.startswith('v') and low[1:].replace('.', '').isdigit():
            out.append(low)
        elif low[:1].isdigit():
            out.append(low.upper())
        else:
            out.append(part[:1].upper() + part[1:])
    return ' '.join(out)


def load_runs():
    runs = []
    for path in glob.glob(str(RECORDS / '*.json')):
        try:
            record = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        if record.get('status') != 'completed':
            continue
        if record.get('stage') not in ('formal', 'pilot'):
            continue
        if any(record.get(key) is None for key in METRICS):
            continue
        runs.append(dict(
            model=record['model_key'], mode=record['mode'], flow=record['traffic_id'],
            seed=int(record['seed']), att=record['att'], awt=record['awt'], aql=record['aql'],
            fallback_rate=record.get('fallback_rate') or 0.0,
            source='record', record=record))
    if LEGACY_CSV.is_file():
        with LEGACY_CSV.open() as stream:
            for row in csv.DictReader(stream):
                if row.get('status') != 'completed':
                    continue
                try:
                    metrics = {key: float(row[key]) for key in METRICS}
                except (KeyError, TypeError, ValueError):
                    continue
                runs.append(dict(
                    model=row['model_key'], mode=row['mode'], flow=row['traffic_id'],
                    seed=int(row['seed']), fallback_rate=0.0,
                    source='legacy', row=row, **metrics))
    return runs


def aggregate(runs):
    groups: dict = {}
    for run in runs:
        groups.setdefault((run['model'], run['flow'], run['mode']), []).append(run)
    aggregates = []
    for (model, flow, mode), members in sorted(groups.items()):
        members.sort(key=lambda r: r['seed'])
        metrics = {}
        for key in METRICS:
            values = [m[key] for m in members]
            metrics[key] = dict(
                mean=sum(values) / len(values),
                sd=statistics.stdev(values) if len(values) > 1 else 0.0)
        aggregates.append(dict(
            model=model, flow=flow, mode=mode,
            seeds=[m['seed'] for m in members], n=len(members), metrics=metrics))
    return aggregates


def published_runs(runs):
    out = []
    for run in sorted(runs, key=lambda r: (r['model'], r['flow'], r['mode'], r['seed'])):
        entry = dict(model=run['model'], mode=run['mode'], flow=run['flow'],
                     seed=run['seed'], att=run['att'], awt=run['awt'], aql=run['aql'],
                     fallback_rate=run['fallback_rate'])
        record = run.get('record')
        if record:
            summary = record.get('summary_path')
            if summary and Path(summary).is_file():
                entry['summary_sha256'] = hashlib.sha256(Path(summary).read_bytes()).hexdigest()
            entry['batch_size'] = record.get('pilot_batch_size')
        out.append(entry)
    return out


def load_baselines():
    """Aggregates for the traditional baselines, published by export_baselines.py.

    They are kept as mode ``baseline`` so they never enter the JevLight /
    CoJevLight table, but they are scored on the same per-(flow, metric) columns
    as the decision models.
    """
    if not BASELINES.is_file():
        return [], []
    document = json.loads(BASELINES.read_text())
    aggregates = []
    for entry in document.get('aggregates', []):
        aggregates.append(dict(model=entry['model'], flow=entry['flow'], mode='baseline',
                               seeds=entry['seeds'], n=entry['n'], metrics=entry['metrics']))
    models = [dict(id=m['id'], name=m['name'], kind='baseline')
              for m in document.get('models', [])]
    return aggregates, models


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true', help='replace assets/benchmark.json')
    parser.add_argument('--summary-only', action='store_true')
    args = parser.parse_args()

    existing = json.loads(BENCHMARK.read_text()) if BENCHMARK.is_file() else {}
    runs = load_runs()
    new_models = {r['model'] for r in runs}
    newest = aggregate(runs)
    baseline_aggregates, baseline_models = load_baselines()
    baselined = {m['id'] for m in baseline_models}

    # Keep published models that this checkout has no results for: their numbers
    # came from elsewhere and must not silently disappear from the page. The
    # baseline mode is the exception: baselines.json is its only source, so a
    # baseline it no longer lists (e.g. a renamed id) is dropped, not kept.
    new_keys = {(a['model'], a['flow'], a['mode']) for a in newest}
    kept = [a for a in existing.get('aggregates', [])
            if (a['model'], a['flow'], a['mode']) not in new_keys and a['mode'] != 'baseline']

    names = display_names()
    baseline_names = {m['id']: m['name'] for m in baseline_models}
    models = []
    for model in sorted(new_models | {a['model'] for a in kept} | baselined):
        previous = next((m for m in existing.get('models', []) if m['id'] == model), None)
        models.append(dict(id=model,
                           name=baseline_names.get(model) or (previous or {}).get('name')
                                or names.get(model)
                                or NAME_OVERRIDES.get(model) or default_name(model),
                           kind='baseline' if model in baselined
                                else (previous or {}).get('kind', 'native')))

    aggregates = sorted(newest + baseline_aggregates + kept,
                        key=lambda a: (a['model'], a['flow'], a['mode']))
    published = published_runs([r for r in runs if r['source'] == 'record'])

    print('records aggregated : %d runs' % len(runs))
    print('baseline groups    : %d (%d models)' % (len(baseline_aggregates), len(baseline_models)))
    print('models             : %d published, %d from this checkout' % (len(models), len(new_models)))
    print('aggregate groups   : %d rebuilt + %d kept = %d' % (len(newest), len(kept), len(aggregates)))
    if args.summary_only:
        return

    payload = dict(
        schema_version=existing.get('schema_version', 1),
        updated_at=datetime.now(timezone.utc).isoformat(),
        protocol=existing.get('protocol', {}),
        flows=existing.get('flows', []),
        models=models,
        aggregates=aggregates,
        runs=published)
    if args.write:
        BENCHMARK.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        print('wrote', BENCHMARK.relative_to(ROOT))


if __name__ == '__main__':
    main()
