"""Build the composite index and the cost plane from the published benchmark matrix.

Traffic metrics are not comparable across scenes: a queue of 20 vehicles in
Hangzhou and 4,000 in New York are both "bad", but on wildly different scales,
and ATT/AWT/AQL each span roughly an order of magnitude across the model pool.
Averaging raw numbers would just report which scene dominates, so every
(traffic flow, metric) cell is normalised on its own, on a log scale:

    score_cell = 100 * (ln hi - ln x) / (ln hi - ln lo)

``lo``/``hi`` are the best and worst values observed in that cell across every
published configuration.  Lower is better for ATT/AWT/AQL, so the best
observation scores 100 and the worst scores 0.  A configuration's composite
score is the unweighted mean of its 21 cells (7 flows x 3 metrics), which puts
every scene and every metric on equal footing.

Cost comes from ``assets/telemetry.json`` (see ``collect_telemetry.py``):
serving time for a whole task times the GPUs it held.  Per flow, the three
seeds are reduced with a median; the seven flows are then averaged, matching
the equal-scene weighting of the score.  Hosted APIs are kept out of the
compute-cost plane because their hardware is not ours to measure.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / 'assets/benchmark.json'
TELEMETRY = ROOT / 'assets/telemetry.json'
OUT = ROOT / 'assets/composite.json'

METRICS = ('att', 'awt', 'aql')
METRIC_LABELS = {'att': 'Travel time', 'awt': 'Waiting time', 'aql': 'Queue length'}
MODES = ('cojevlight', 'jevlight')

# Display names the id alone cannot produce faithfully.
NAME_OVERRIDES = {
    'd3': 'D3', 'd3-flash': 'D3 Flash', 'lev': 'Lev', 'von': 'Von',
    'gliner2.5-decide': 'GLiNER2.5-Decide', 'jev-api': 'Jev API',
    'open-jev-2b': 'Open-JEV 2B', 'open-jev-9b': 'Open-JEV 9B',
    'open-jev-27b': 'Open-JEV 27B', 'bespoke-nimble-9b': 'Bespoke-Nimble 9B',
    'laya-multilingual': 'Laya Multilingual', 'agent-jev': 'Agent-JEV',
    'maxpressure': 'MaxPressure', 'decider-4b': 'Decider 4B',
    'clef-27b': 'Clef 27B', 'clef-flash': 'Clef Flash',
    'pplx-decider-v1.2': 'PPLX Decider v1.2',
    'pplx-decider-flash-v1.2': 'PPLX Decider Flash v1.2',
}

# Family -> label, colour.  Colours stay distinguishable on the dark page.
FAMILIES = (
    ('startlux', 'StartLux', '#3ddc84'),
    ('kev', 'Kev', '#ffc531'),
    ('valen', 'Valen', '#6cb6ff'),
    ('open-jev', 'Open-JEV', '#c792ea'),
    ('clef', 'Clef', '#ff8a65'),
    ('pplx', 'PPLX', '#f06292'),
    ('d3', 'D3', '#4dd0e1'),
    ('decider', 'Decider', '#aed581'),
    ('laya', 'Laya', '#ffd54f'),
    ('lev', 'Lev', '#90a4ae'),
    ('bespoke', 'Bespoke', '#ba68c8'),
    ('agent-jev', 'Agent-JEV', '#e57373'),
    ('von', 'Von', '#81c784'),
    ('gliner', 'GLiNER', '#4fc3f7'),
    ('jev-api', 'Jev API', '#e8eef5'),
    ('maxpressure', 'MaxPressure', '#8a99a8'),
)


def family_of(model_id: str) -> str:
    if model_id in ('maxpressure', 'jev-api'):
        return model_id
    if model_id.startswith('pplx'):
        return 'pplx'
    if model_id.startswith('open-jev'):
        return 'open-jev'
    for prefix, _, _ in FAMILIES:
        if model_id.startswith(prefix) and prefix not in ('maxpressure', 'jev-api'):
            return prefix
    return model_id


def family_meta(family: str):
    for key, label, colour in FAMILIES:
        if key == family:
            return label, colour
    return family, '#8a99a8'


def display_name(model_id: str, published: dict) -> str:
    return published.get(model_id) or NAME_OVERRIDES.get(model_id) or model_id


def params_b(name: str) -> float | None:
    match = re.search(r'(\d+(?:\.\d+)?)\s*B\b', name)
    return float(match.group(1)) if match else None


def cell_score(value: float, lo: float, hi: float) -> float:
    if not (value > 0 and lo > 0 and hi > 0):
        return 0.0
    if hi <= lo:
        return 100.0
    score = (math.log(hi) - math.log(value)) / (math.log(hi) - math.log(lo)) * 100.0
    return max(0.0, min(100.0, score))


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def pareto(points: list) -> list:
    """Keep the configurations no other one beats on both cost and score."""
    ordered = sorted(points, key=lambda p: (p['cost']['gpu_seconds'], -p['score']))
    frontier, best = [], -1.0
    for point in ordered:
        if point['score'] > best:
            frontier.append(point['id'])
            best = point['score']
    return frontier


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark', default=str(BENCHMARK))
    parser.add_argument('--telemetry', default=str(TELEMETRY))
    parser.add_argument('--out', default=str(OUT))
    args = parser.parse_args()

    bench = json.loads(Path(args.benchmark).read_text(encoding='utf-8'))
    telemetry = json.loads(Path(args.telemetry).read_text(encoding='utf-8'))
    flows = [f['id'] for f in bench['flows']]
    flow_names = {f['id']: f['name'] for f in bench['flows']}
    flow_sizes = {f['id']: f.get('intersections') for f in bench['flows']}
    published = {m['id']: m['name'] for m in bench['models']}
    kinds = {m['id']: m['kind'] for m in bench['models']}

    groups: dict[tuple, dict] = {}
    for entry in bench['aggregates']:
        groups.setdefault((entry['model'], entry['mode']), {})[entry['flow']] = entry['metrics']

    # Column bounds over every published configuration.
    columns = {}
    for flow in flows:
        for metric in METRICS:
            values = [g[flow][metric]['mean'] for g in groups.values() if flow in g]
            columns[(flow, metric)] = (min(values), max(values))

    # Serving telemetry grouped per configuration and per flow.
    carries: dict[tuple, dict] = {}
    for run in telemetry['runs']:
        carries.setdefault((run['model'], run['mode']), {}).setdefault(run['flow'], []).append(run)

    def gpus_for(model: str, mode: str) -> int:
        values = [r.get('gpus') for pair, by_flow in carries.items()
                  if pair[0] == model for runs in by_flow.values() for r in runs]
        values = [v for v in values if v]
        if values:
            return int(median(values))
        return 1

    configs = []
    for (model, mode), by_flow in groups.items():
        if mode == 'maxpressure':
            continue
        if sorted(by_flow) != sorted(flows):
            raise SystemExit(f'{model} [{mode}] does not cover every flow')
        cells, scores = {}, []
        for flow in flows:
            cells[flow] = {}
            for metric in METRICS:
                entry = by_flow[flow][metric]
                score = cell_score(entry['mean'], *columns[(flow, metric)])
                cells[flow][metric] = dict(raw=round(entry['mean'], 3),
                                           sd=round(entry.get('sd') or 0.0, 3),
                                           score=round(score, 2))
                scores.append(score)
        composite = round(sum(scores) / len(scores), 2)

        runs_by_flow = carries.get((model, mode), {})
        hosted = kinds.get(model) == 'api' or model == 'jev-api'
        gpus = gpus_for(model, mode)
        cost_by_flow = {}
        for flow in flows:
            runs = runs_by_flow.get(flow, [])
            serving = median([r['serving_s'] for r in runs if r.get('serving_s') is not None])
            if serving is None or hosted:
                cost_by_flow[flow] = None
            else:
                cost_by_flow[flow] = round(serving * gpus, 1)
        gpu_seconds = mean(cost_by_flow.values())
        walls = [r['wall_s'] for runs in runs_by_flow.values() for r in runs if r.get('wall_s') is not None]
        serving_all = [r['serving_s'] for runs in runs_by_flow.values() for r in runs if r.get('serving_s') is not None]
        tokens_by_flow = {}
        for flow in flows:
            tokens = median([r['tokens_in'] for r in runs_by_flow.get(flow, []) if r.get('tokens_in')])
            tokens_by_flow[flow] = tokens
        tokens = mean(tokens_by_flow.values())
        decisions = mean([median([r['decisions'] for r in runs if r.get('decisions')])
                          for runs in runs_by_flow.values()])
        cost = dict(
            gpu_seconds=round(gpu_seconds, 1) if gpu_seconds is not None else None,
            serving_seconds=round(median(serving_all), 1) if serving_all else None,
            wall_seconds=round(median(walls), 1) if walls else None,
            tokens_per_task=int(round(tokens)) if tokens else None,
            decisions_per_task=int(round(decisions)) if decisions else None,
            tokens_per_decision=round(tokens / decisions, 1) if tokens and decisions else None,
            gpus=None if hosted else gpus, hosted=hosted,
            runs=sum(len(v) for v in runs_by_flow.values()),
            by_flow=cost_by_flow,
        )
        name = display_name(model, published)
        label, colour = family_meta(family_of(model))
        configs.append(dict(
            id=f'{model}::{mode}', model=model, mode=mode, name=name,
            family=family_of(model), family_label=label, color=colour,
            kind=kinds.get(model, 'native'), hosted=hosted,
            params_b=params_b(name), score=composite, cells=cells, cost=cost,
        ))

    configs.sort(key=lambda c: (-c['score'], c['name']))
    for index, config in enumerate(configs, 1):
        config['rank'] = index

    ranked = [c for c in configs if not c['hosted'] and c['cost']['gpu_seconds']]
    frontier = pareto(ranked)
    for config in configs:
        config['pareto'] = config['id'] in frontier

    # MaxPressure: the reference line, no model compute.
    baseline = None
    for (model, mode), by_flow in groups.items():
        if mode != 'maxpressure':
            continue
        cells, scores = {}, []
        for flow in flows:
            cells[flow] = {}
            for metric in METRICS:
                raw = by_flow[flow][metric]['mean']
                score = cell_score(raw, *columns[(flow, metric)])
                cells[flow][metric] = dict(raw=round(raw, 3), score=round(score, 2))
                scores.append(score)
        baseline = dict(id=model, name=published.get(model, 'MaxPressure'),
                        score=round(sum(scores) / len(scores), 2), cells=cells)

    payload = dict(
        schema_version=1,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source=dict(
            benchmark=Path(args.benchmark).name,
            telemetry=Path(args.telemetry).name,
            benchmark_updated_at=bench.get('updated_at'),
            configurations=len(configs),
            telemetry_runs=len(telemetry['runs']),
            seeds=3,
            procedure='SUMO, 3,600 s episode, 240 control steps, 3 seeds per condition',
        ),
        method=dict(
            normalisation='Per (flow, metric) log min-max over every published configuration. '
                          'Best observed = 100, worst observed = 0.',
            aggregation='Unweighted mean of the 21 cell scores (7 flows x 3 metrics).',
            cost='Per flow: median over the three seeds of serving time x GPUs held; '
                 'then averaged over the seven flows.',
            frontier='Configurations not dominated on (cost, score) among self-hosted models.',
        ),
        metrics=[dict(key=k, label=v) for k, v in METRIC_LABELS.items()],
        flows=[dict(id=f, name=flow_names[f], intersections=flow_sizes[f]) for f in flows],
        columns=[dict(flow=f, metric=m, min=columns[(f, m)][0], max=columns[(f, m)][1])
                 for f in flows for m in METRICS],
        modes=[dict(id=m, label='CoJevLight' if m == 'cojevlight' else 'JevLight') for m in MODES],
        configs=configs,
        pareto=frontier,
        baseline=baseline,
    )

    out = Path(args.out)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    # The page loads this with a plain <script> tag so it also works from
    # file://, where fetch() of a local JSON file is blocked.
    script = out.with_suffix('.js')
    script.write_text('window.JEV_COMPOSITE = '
                      + json.dumps(payload, ensure_ascii=False, indent=1) + ';\n', encoding='utf-8')

    print(f"{len(configs)} configurations, {len(frontier)} on the frontier -> {out}")
    for config in configs:
        cost = config['cost']
        gpu = f"{cost['gpu_seconds']:8.0f}" if cost['gpu_seconds'] else '       -'
        mark = '*' if config['pareto'] else ' '
        print(f"{mark}{config['rank']:3d}. {config['name']:24s} {config['mode']:11s} "
              f"{config['score']:6.2f}  gpu-s {gpu}")
    print(f"   baseline {baseline['name']}: {baseline['score']:.2f}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
