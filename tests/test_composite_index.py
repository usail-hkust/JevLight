"""The composite index must stay reproducible from the published matrix."""
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'scripts/benchmark/build_composite.py'
BENCHMARK = ROOT / 'assets/benchmark.json'
TELEMETRY = ROOT / 'assets/telemetry.json'
COMPOSITE = ROOT / 'assets/composite.json'

pytestmark = pytest.mark.skipif(
    not (BENCHMARK.is_file() and TELEMETRY.is_file()),
    reason='published benchmark and telemetry payloads are not present')


def cell_score(value, lo, hi):
    if hi <= lo:
        return 100.0
    return max(0.0, min(100.0, (math.log(hi) - math.log(value)) / (math.log(hi) - math.log(lo)) * 100.0))


@pytest.fixture(scope='module')
def composite(tmp_path_factory):
    out = tmp_path_factory.mktemp('composite') / 'composite.json'
    subprocess.run([sys.executable, str(BUILD), '--benchmark', str(BENCHMARK),
                    '--telemetry', str(TELEMETRY), '--out', str(out)],
                   check=True, cwd=ROOT, capture_output=True)
    return json.loads(out.read_text(encoding='utf-8'))


def test_every_configuration_covers_every_scene_and_metric(composite):
    flows = [f['id'] for f in composite['flows']]
    metrics = [m['key'] for m in composite['metrics']]
    assert len(flows) * len(metrics) == 21
    for config in composite['configs']:
        assert sorted(config['cells']) == sorted(flows)
        for flow in flows:
            assert sorted(config['cells'][flow]) == sorted(metrics)


def test_scores_are_the_mean_of_their_cells(composite):
    for config in composite['configs']:
        cells = [cell['score'] for flow in config['cells'].values() for cell in flow.values()]
        assert len(cells) == 21
        assert config['score'] == pytest.approx(sum(cells) / len(cells), abs=0.01)


def test_columns_are_normalised_on_their_own_scale(composite):
    bounds = {(c['flow'], c['metric']): (c['min'], c['max']) for c in composite['columns']}
    for config in composite['configs']:
        for flow, cells in config['cells'].items():
            for metric, cell in cells.items():
                expected = cell_score(cell['raw'], *bounds[(flow, metric)])
                assert cell['score'] == pytest.approx(expected, abs=0.01)


def test_baseline_scores_between_the_published_extremes(composite):
    baseline = composite['baseline']
    assert baseline is not None
    scores = [c['score'] for c in composite['configs']]
    assert min(scores) <= baseline['score'] <= max(scores)
    assert baseline['score'] == pytest.approx(
        sum(cell['score'] for flow in baseline['cells'].values() for cell in flow.values()) / 21,
        abs=0.01)


def test_ranking_is_descending_and_dense(composite):
    configs = composite['configs']
    assert [c['rank'] for c in configs] == list(range(1, len(configs) + 1))
    assert all(a['score'] >= b['score'] for a, b in zip(configs, configs[1:]))


def test_frontier_is_actually_pareto_optimal(composite):
    ranked = [c for c in composite['configs'] if not c['hosted'] and c['cost']['gpu_seconds']]
    frontier = set(composite['pareto'])
    assert frontier, 'the cost plane must have a frontier'
    for config in ranked:
        if config['id'] not in frontier:
            continue
        dominated = any(
            other['cost']['gpu_seconds'] <= config['cost']['gpu_seconds']
            and other['score'] >= config['score']
            and (other['cost']['gpu_seconds'] < config['cost']['gpu_seconds']
                 or other['score'] > config['score'])
            for other in ranked if other['id'] != config['id'])
        assert not dominated, f'{config["id"]} is on the frontier but is dominated'
    for config in ranked:
        if config['id'] in frontier:
            continue
        dominated = any(
            other['cost']['gpu_seconds'] <= config['cost']['gpu_seconds']
            and other['score'] >= config['score']
            and (other['cost']['gpu_seconds'] < config['cost']['gpu_seconds']
                 or other['score'] > config['score'])
            for other in ranked if other['id'] != config['id'])
        assert dominated, f'{config["id"]} is off the frontier but nothing dominates it'


def test_hosted_models_are_ranked_but_not_priced(composite):
    hosted = [c for c in composite['configs'] if c['hosted']]
    for config in hosted:
        assert config['cost']['gpu_seconds'] is None
        assert config['id'] not in composite['pareto']


def test_published_file_matches_the_generator(composite):
    if not COMPOSITE.is_file():
        pytest.skip('assets/composite.json has not been generated in this checkout')
    published = json.loads(COMPOSITE.read_text(encoding='utf-8'))
    assert published['configs'] == composite['configs']
    assert published['pareto'] == composite['pareto']


def test_telemetry_is_deduplicated_and_covers_every_group():
    telemetry = json.loads(TELEMETRY.read_text(encoding='utf-8'))
    keys = [(r['model'], r['mode'], r['flow'], r['seed']) for r in telemetry['runs']]
    assert len(keys) == len(set(keys))
    benchmark = json.loads(BENCHMARK.read_text(encoding='utf-8'))
    published = {(a['model'], a['mode'], a['flow']) for a in benchmark['aggregates']
                 if a['mode'] != 'maxpressure'}
    covered = {(r['model'], r['mode'], r['flow']) for r in telemetry['runs']}
    assert published == covered
    for run in telemetry['runs']:
        assert run['steps'] > 0
        assert run['decisions'] >= 0
        assert run['serving_s'] >= 0


def _rank(values):
    order = sorted(values, key=lambda key: -values[key])
    return {key: index + 1 for index, key in enumerate(order)}


def _spearman(left, right):
    keys = sorted(left)
    n = len(keys)
    mean_l = sum(left[k] for k in keys) / n
    mean_r = sum(right[k] for k in keys) / n
    cov = sum((left[k] - mean_l) * (right[k] - mean_r) for k in keys)
    dev_l = math.sqrt(sum((left[k] - mean_l) ** 2 for k in keys))
    dev_r = math.sqrt(sum((right[k] - mean_r) ** 2 for k in keys))
    return cov / (dev_l * dev_r)


def test_ranking_survives_alternative_weightings(composite):
    """The page claims the order is robust; keep that claim honest."""
    metrics = [m['key'] for m in composite['metrics']]
    configs = composite['configs']
    base = {}
    for config in configs:
        cells = [cell['score'] for flow in config['cells'].values() for cell in flow.values()]
        base[config['id']] = sum(cells) / len(cells)

    def reweighted(weights):
        out = {}
        for config in configs:
            total = weight = 0.0
            for flow in config['cells'].values():
                for metric in metrics:
                    total += flow[metric]['score'] * weights[metric]
                    weight += weights[metric]
            out[config['id']] = total / weight
        return out

    def ranks(values):
        order = sorted(values, key=lambda key: -values[key])
        return {key: index + 1 for index, key in enumerate(order)}

    def spearman(left, right):
        keys = sorted(left)
        n = len(keys)
        mean_l = sum(left[k] for k in keys) / n
        mean_r = sum(right[k] for k in keys) / n
        cov = sum((left[k] - mean_l) * (right[k] - mean_r) for k in keys)
        dev_l = math.sqrt(sum((left[k] - mean_l) ** 2 for k in keys))
        dev_r = math.sqrt(sum((right[k] - mean_r) ** 2 for k in keys))
        return cov / (dev_l * dev_r)

    base_ranks = ranks(base)
    modes = [m['id'] for m in composite['modes']]

    # A balanced reweighting must not disturb the leaders within either mode.
    balanced_scores = reweighted({'att': 0.5, 'awt': 0.3, 'aql': 0.2})
    balanced = ranks(balanced_scores)
    assert spearman(base_ranks, balanced) >= 0.99
    for mode in modes:
        ids = [c['id'] for c in configs if c['mode'] == mode]
        assert set(sorted(ids, key=lambda k: -base[k])[:10]) == \
               set(sorted(ids, key=lambda k: -balanced_scores[k])[:10]), mode

    # Even collapsing to one metric keeps the overall order broadly intact,
    # which is the claim the page makes (rho >= 0.97 within a mode).
    for metric in metrics:
        weights = {key: (1.0 if key == metric else 0.0) for key in metrics}
        variant = ranks(reweighted(weights))
        for mode in modes:
            ids = [c['id'] for c in configs if c['mode'] == mode]
            rho = spearman({k: base_ranks[k] for k in ids}, {k: variant[k] for k in ids})
            assert rho >= 0.95, (metric, mode, rho)


def test_placeholders_are_filled_without_rebuilding_the_section():
    """The page never rebuilds #index: its .reveal nodes are already observed.

    Rewriting section.innerHTML detached the nodes the page's IntersectionObserver
    was watching, so the copy stayed at opacity 0 and left a blank gap above
    Quick start.
    """
    import re

    script = (ROOT / 'assets/composite-chart.js').read_text(encoding='utf-8')
    body = script.split('function fillPlaceholders()', 1)[1].split('\n  }', 1)[0]
    body = re.sub(r'/\*.*?\*/|//[^\n]*', '', body, flags=re.S)
    assert not re.search(r'section\.innerHTML\s*=', body)
    assert 'nodeValue' in body
