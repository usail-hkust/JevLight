"""Merge visual-agent serving telemetry into the published telemetry payload.

The visual campaign records one model request per intersection for perception
and one for the phase decision. Its summaries carry the total request count and
mean request latency, so the serving time for a condition is estimated as
``requests * mean_latency / concurrency`` with the protocol's eight in-flight
requests. This is the same wall-clock quantity the text runs measure as the
slowest request in each control step; the estimate is used because the visual
decision logs are multi-gigabyte per New York condition and are not stored in
this checkout.

Usage::

    python -m scripts.benchmark.merge_visual_telemetry \
        --runs visual_runs.json --write
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY = ROOT / 'assets/telemetry.json'
BENCHMARK = ROOT / 'assets/benchmark.json'

CONCURRENCY = 8          # protocol: eight in-flight requests per condition
GPUS_PER_CONDITION = 1   # each condition owns one GPU-share of the model pool


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True,
                        help='per-seed export from the visual formal records')
    parser.add_argument('--telemetry', default=str(TELEMETRY))
    parser.add_argument('--benchmark', default=str(BENCHMARK))
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()

    payload = json.loads(Path(args.telemetry).read_text(encoding='utf-8'))
    benchmark = json.loads(Path(args.benchmark).read_text(encoding='utf-8'))
    intersections = {flow['id']: flow.get('intersections') for flow in benchmark['flows']}

    rows = json.loads(args.runs.read_text(encoding='utf-8'))
    rows = rows.get('rows') or rows
    entries = []
    for run in rows:
        flow = run['flow']
        steps = int(run['steps'])
        decisions = int(intersections[flow]) * steps if intersections.get(flow) else None
        requests = run.get('requests')
        latency = run.get('latency_mean_s')
        serving = round(float(requests) * float(latency) / CONCURRENCY, 3) \
            if requests and latency else None
        entries.append(dict(
            id=f"{run['model']}_vlalight_{flow}_s{run['seed']}",
            model=run['model'], mode='vlalight', flow=flow, seed=int(run['seed']),
            source='visual_formal', wall_s=run.get('wall_s'),
            gpus=GPUS_PER_CONDITION, batch_size=1, steps=steps,
            decisions=decisions, fallbacks=run.get('fallback_count') or 0,
            tokens_in=int(run.get('input_tokens') or 0),
            serving_s=serving,
        ))

    kept = [run for run in payload['runs'] if run.get('mode') != 'vlalight']
    out = dict(
        schema_version=payload.get('schema_version', 1),
        description=payload.get('description'),
        semantics=payload.get('semantics'),
        runs=sorted(kept + entries, key=lambda r: (r['model'], r['mode'], r['flow'], r['seed'])),
        totals=dict(runs=len(kept) + len(entries),
                    recovered=payload.get('totals', {}).get('recovered') or 0,
                    unrecovered=len(payload.get('notes', {}).get('unrecovered') or [])),
        notes=payload.get('notes') or {},
        visual=dict(
            updated_at=datetime.now(timezone.utc).isoformat(),
            concurrency=CONCURRENCY,
            gpus_per_condition=GPUS_PER_CONDITION,
            basis='requests x mean request latency / 8 in-flight requests; '
                  'rendering and simulator time are excluded.',
        ),
    )
    if args.write:
        Path(args.telemetry).write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n',
                                        encoding='utf-8')
        print(f'{len(entries)} visual runs merged -> {args.telemetry}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
