"""Publish the Baseline-A40 campaign results into the benchmark matrix.

The RL and rule-based baselines run from their own queue
(``scripts.experiments.baseline_a40_queue``) on a separate checkout, so their
records live under ``results/experiments/baselines_a40`` and are git-ignored.
This module turns a dumped export of those records into
``assets/baselines.json``, the tracked input ``build_benchmark.py`` merges.

Every run is one (model, flow, seed) evaluation on the same benchmark protocol
as the JevLight matrix: SUMO, 3,600 s episode, three seeds. Baselines have a
single mode, recorded as ``baseline``, so they never mix into the
JevLight/CoJevLight comparison table while still being scored on the same
per-(flow, metric) columns.

Two controllers are both called MaxPressure and must not share an id. The
campaign's ``--baseline maxpressure`` is ``baselines/maxpressure.py``, the
strict upstream-minus-downstream lane pressure, published as
``maxpressure-strict``. ``maxpressure`` stays the benchmark's own controller
(``run_jevlight.py --dry_run``, queue plus approaching vehicles), the dashed
reference line on the page; its runs come from a separate export.

Usage::

    python -m scripts.benchmark.export_baselines \\
        --runs campaign.json --runs maxpressure.json --write
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets/baselines.json'

METRICS = ('att', 'awt', 'aql')

# Ids whose display name the default transformation cannot produce faithfully.
NAME_OVERRIDES = {
    'advanceddqn': 'AdvancedDQN',
    'attendlight': 'AttendLight',
    'citylight': 'CityLight',
    'colight': 'CoLight',
    'fixedtime': 'FixedTime',
    'maxpressure': 'MaxPressure',
    'maxpressure-strict': 'MaxPressure (strict)',
    'mplight': 'MPLight',
    'presslight': 'PressLight',
    'webster': 'Webster',
}

# Kept apart from the model families: these are traditional controllers, not
# LLM decision models.
FAMILY = {'id': 'baseline', 'label': 'Traditional', 'colour': '#8a99a8'}


def display_name(identifier: str) -> str:
    return NAME_OVERRIDES.get(identifier, identifier.replace('-', ' ').title())


def model_id(run: dict) -> str:
    """The published id; the strict MaxPressure must not shadow the benchmark's."""
    if run['model'] == 'maxpressure' and 'baselines.run_baseline' in (run.get('args') or []):
        return 'maxpressure-strict'
    return run['model']


def aggregate(runs: list[dict]) -> list[dict]:
    """One entry per (model, flow): mean and sample SD over the seeds."""
    groups: dict[tuple, list[dict]] = {}
    for run in runs:
        groups.setdefault((run['model'], run['flow']), []).append(run)
    out = []
    for (model, flow), members in sorted(groups.items()):
        members.sort(key=lambda r: r['seed'])
        metrics = {}
        for key in METRICS:
            values = [m[key] for m in members]
            metrics[key] = dict(mean=sum(values) / len(values),
                                sd=statistics.stdev(values) if len(values) > 1 else 0.0)
        out.append(dict(model=model, flow=flow, mode='baseline',
                        seeds=[m['seed'] for m in members], n=len(members),
                        metrics=metrics))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True, action='append',
                        help='export of eval records ({"runs": [...]}); repeatable')
    parser.add_argument('--write', action='store_true', help=f'replace {OUT.relative_to(ROOT)}')
    parser.add_argument('--summary-only', action='store_true')
    args = parser.parse_args()

    runs = []
    for path in args.runs:
        payload = json.loads(path.read_text())
        for run in payload.get('runs') or payload:
            if any(run.get(key) is None for key in METRICS):
                continue
            runs.append(dict(model=model_id(run), flow=run['flow'], seed=int(run['seed']),
                             att=run['att'], awt=run['awt'], aql=run['aql'],
                             fallback_rate=run.get('fallback_rate') or 0.0,
                             wall_s=run.get('wall_s')))
    if not runs:
        raise SystemExit('no runs with metrics in the export')
    keys = [(run['model'], run['flow'], run['seed']) for run in runs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise SystemExit(f'duplicate (model, flow, seed) across exports: {duplicates[:5]}')

    aggregates = aggregate(runs)
    models = []
    for model in sorted({run['model'] for run in runs}):
        models.append(dict(id=model, name=display_name(model), kind='baseline'))

    print('runs        : %d' % len(runs))
    print('models      : %d' % len(models))
    print('aggregates  : %d groups' % len(aggregates))
    seeds = sorted({run['seed'] for run in runs})
    print('seeds       : %s' % seeds)
    if args.summary_only:
        return 0

    document = dict(
        schema_version=1,
        updated_at=datetime.now(timezone.utc).isoformat(),
        source=dict(campaign='baseline-a40', flows=7, seeds=len(seeds),
                    protocol='SUMO, 3,600 s episode, 3 seeds per condition'),
        family=FAMILY,
        models=models,
        aggregates=aggregates,
        runs=sorted(runs, key=lambda r: (r['model'], r['flow'], r['seed'])))
    if args.write:
        OUT.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n')
        print('wrote', OUT.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
