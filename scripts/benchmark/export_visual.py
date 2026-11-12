"""Publish the visual-agent campaign results into the benchmark matrix.

The VLALight campaign runs one rendered-camera agent per model: the three open
vision models from the Visual JevLight branch (WeMM-JEV, d3-turbo and Amos 1
Large) plus the collaborator's VLALight-4B. Every condition uses the same SUMO
episode, 15-second control interval and three seeds as the text benchmark, and
enables visual cooperation, so the runs publish as the ``vlalight`` mode.

The raw per-seed export comes from the vision queue's ``formal/completed``
records and their ``summary.json`` files. Only the three traffic metrics and
the run wall time leave those summaries; prompts and images stay in the
campaign checkouts.

Usage::

    python -m scripts.benchmark.export_visual \
        --runs visual_runs.json --write
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets/visual.json'

METRICS = ('att', 'awt', 'aql')
MODE = 'vlalight'

# Ids come from the campaign's model keys; the display names are the ones the
# visual branch uses in its reports.
NAME_OVERRIDES = {
    'amos-1-large': 'Amos 1 Large',
    'd3-turbo': 'D3-Turbo',
    'vlalight-4b': 'VLALight-4B',
    'wemm-jev': 'WeMM-JEV',
}


def display_name(identifier: str) -> str:
    return NAME_OVERRIDES.get(identifier, identifier.replace('-', ' ').title())


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
        out.append(dict(model=model, flow=flow, mode=MODE,
                        seeds=[m['seed'] for m in members], n=len(members),
                        metrics=metrics))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True, action='append',
                        help='per-seed export ({"rows": [...]}); repeatable')
    parser.add_argument('--write', action='store_true', help=f'replace {OUT.relative_to(ROOT)}')
    parser.add_argument('--summary-only', action='store_true')
    args = parser.parse_args()

    runs = []
    for path in args.runs:
        payload = json.loads(path.read_text())
        for run in payload.get('rows') or payload:
            if any(run.get(key) is None for key in METRICS):
                continue
            runs.append(dict(model=run['model'], flow=run['flow'], seed=int(run['seed']),
                             att=run['att'], awt=run['awt'], aql=run['aql'],
                             fallback_rate=run.get('fallback_count') or 0.0,
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
        models.append(dict(id=model, name=display_name(model), kind='visual'))

    seeds = sorted({run['seed'] for run in runs})
    print('runs        : %d' % len(runs))
    print('models      : %d' % len(models))
    print('aggregates  : %d groups' % len(aggregates))
    print('seeds       : %s' % seeds)
    if args.summary_only:
        return 0

    document = dict(
        schema_version=1,
        updated_at=datetime.now(timezone.utc).isoformat(),
        source=dict(campaign='vlalight-vision', flows=7, seeds=len(seeds),
                    protocol='SUMO, 3,600 s episode, 15 s control interval, '
                             'three seeds per condition',
                    observations='Rendered cameras + VLALight two-stage visual '
                                 'agent with visual cooperation.'),
        mode=MODE,
        models=models,
        aggregates=aggregates,
        runs=sorted(runs, key=lambda r: (r['model'], r['flow'], r['seed'])))
    if args.write:
        OUT.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n')
        print('wrote', OUT.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
