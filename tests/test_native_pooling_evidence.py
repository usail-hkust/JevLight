"""CPU protocol/driver regressions; these do not establish GPU acceptance."""
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from jevlight.backends.native_pooling_evidence import WorkerEvidence


def journals(tmp_path, count=2):
    armed = []
    for rank in range(count):
        report = dict(step_id='step', rank=rank, pid=os.getpid(),
                      start_ticks=Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19],
                      device=f'cuda:{rank}', gpu_uuid=f'GPU-uuid-{rank}',
                      initial_free_bytes=400, initial_reserved_bytes=600, memory_total_bytes=1000,
                      evidence_path=str(tmp_path / f'rank-{rank}.jsonl'))
        append(report, event='armed')
        armed.append(report)
    return armed


def append(report, **event):
    value = {key: val for key, val in report.items() if key != 'evidence_path'}
    value.update(event)
    with open(report['evidence_path'], 'a') as stream:
        stream.write(json.dumps(value) + '\n')


def forward(report, **overrides):
    append(report, **(dict(event='forward_completed', chunk=1, rows=3, input_tokens=99,
                          completed_at_ns=123, memory_allocated_bytes=500,
                          memory_reserved_bytes=600, memory_free_bytes=400,
                          memory_peak_allocated_bytes=550, memory_peak_reserved_bytes=650,
                          memory_total_bytes=1000) | overrides))


def reader(armed, tmp_path, notify=None):
    return WorkerEvidence(armed, [f'uuid-{rank}' for rank in range(len(armed))],
                          'step', tmp_path, notify)


def test_progress_requires_completed_matching_chunks_on_every_rank(tmp_path):
    armed = journals(tmp_path)
    notifications = []
    evidence = reader(armed, tmp_path, lambda: notifications.append('chunk'))
    evidence.poll()
    forward(armed[0])
    evidence.poll()
    assert not notifications and not evidence.completed
    forward(armed[1])
    evidence.poll()
    evidence.poll()
    assert notifications == ['chunk']
    assert [event['rank'] for event in evidence.completed[0]] == [0, 1]
    reports = []
    for report in armed:
        append(report, event='disarmed', completed_chunks=1)
        reports.append(dict(report, forwards=evidence.workers[report['rank']]['forwards']))
    evidence.finish(reports)
    assert len(evidence.completed) == 1


@pytest.mark.parametrize('failure', ['missing', 'duplicate', 'uuid', 'step', 'start', 'path'])
def test_rejects_wrong_worker_registration(tmp_path, failure):
    armed = journals(tmp_path)
    if failure == 'missing':
        armed.pop()
    elif failure == 'duplicate':
        armed[1] = armed[0]
    elif failure == 'uuid':
        armed[1]['gpu_uuid'] = 'other-gpu'
    elif failure == 'step':
        armed[1]['step_id'] = 'stale-step'
    elif failure == 'start':
        armed[1]['start_ticks'] = '0'
    else:
        armed[1]['evidence_path'] = str(tmp_path.parent / 'outside')
    with pytest.raises(ValueError):
        WorkerEvidence(armed, ['uuid-0', 'uuid-1'], 'step', tmp_path)


@pytest.mark.parametrize('override', [dict(step_id='stale'), dict(chunk=2), dict(rows=0),
                                     dict(input_tokens=None), dict(memory_free_bytes=-1),
                                     dict(memory_allocated_bytes=700),
                                     dict(memory_peak_allocated_bytes=None),
                                     dict(memory_peak_allocated_bytes=499),
                                     dict(memory_peak_reserved_bytes=599),
                                     dict(memory_peak_allocated_bytes=700)])
def test_invalid_event_never_emits_progress(tmp_path, override):
    armed = journals(tmp_path, 1)
    notifications = []
    evidence = reader(armed, tmp_path, lambda: notifications.append(1))
    forward(armed[0], **override)
    with pytest.raises(ValueError):
        evidence.poll()
    assert not notifications


def test_mismatched_tp_mapping_is_rejected(tmp_path):
    armed = journals(tmp_path)
    evidence = reader(armed, tmp_path)
    forward(armed[0])
    forward(armed[1], input_tokens=100)
    with pytest.raises(ValueError, match='mapping'):
        evidence.poll()


def test_memory_reports_each_rank_and_keeps_incomplete_attempt(tmp_path):
    armed = journals(tmp_path)
    evidence = reader(armed, tmp_path)
    assert all(report['peak_allocated_bytes'] is None for report in evidence.memory_summary())
    forward(armed[0], memory_peak_reserved_bytes=800)
    evidence.poll()
    reports = evidence.memory_summary()
    assert reports[0]['peak_reserved_bytes'] == 800
    assert reports[0]['min_observed_free_bytes'] == 400
    assert reports[1]['peak_reserved_bytes'] is None
    assert not evidence.completed  # Partial TP execution never becomes progress.
    forward(armed[1], memory_free_bytes=300)
    evidence.poll()
    reports = evidence.memory_summary()
    assert [report['completed_chunks'] for report in reports] == [1, 1]
    assert [report['min_observed_free_bytes'] for report in reports] == [400, 300]
    assert [report['gpu_uuid'] for report in reports] == ['GPU-uuid-0', 'GPU-uuid-1']


def test_peak_counters_cannot_reset_within_a_step(tmp_path):
    armed = journals(tmp_path, 1)
    evidence = reader(armed, tmp_path)
    forward(armed[0], memory_peak_reserved_bytes=800)
    evidence.poll()
    forward(armed[0], chunk=2, memory_peak_reserved_bytes=700)
    with pytest.raises(ValueError, match='peak memory decreased'):
        evidence.poll()


def test_partial_live_line_waits_for_completed_append(tmp_path):
    armed = journals(tmp_path, 1)
    evidence = reader(armed, tmp_path)
    forward(armed[0])
    path = Path(armed[0]['evidence_path'])
    full = path.read_bytes()
    path.write_bytes(full[:-2])
    evidence.poll()
    assert not evidence.completed
    with path.open('ab') as stream:
        stream.write(full[-2:])
    evidence.poll()
    assert len(evidence.completed) == 1


def test_empty_and_unbalanced_worker_reports_cannot_pass(tmp_path):
    armed = journals(tmp_path)
    evidence = reader(armed, tmp_path)
    reports = []
    for report in armed:
        append(report, event='disarmed', completed_chunks=0)
        reports.append(dict(report, forwards=[]))
    with pytest.raises(ValueError, match='No complete'):
        evidence.finish(reports)


@pytest.mark.parametrize('failure', ['missing_rank', 'changed_forward', 'incomplete_tail', 'changed_baseline'])
def test_finish_reconciles_rpc_with_complete_journal(tmp_path, failure):
    armed = journals(tmp_path)
    evidence = reader(armed, tmp_path)
    reports = []
    for report in armed:
        forward(report)
        evidence.poll()
        append(report, event='disarmed', completed_chunks=1)
        reports.append(dict(report, forwards=list(evidence.workers[report['rank']]['forwards'])))
    if failure == 'missing_rank':
        reports.pop()
    elif failure == 'changed_forward':
        reports[1]['forwards'] = []
    elif failure == 'changed_baseline':
        reports[1]['initial_free_bytes'] += 1
    else:
        with open(armed[1]['evidence_path'], 'a') as stream:
            stream.write('{"partial"')
    with pytest.raises(ValueError, match='finish'):
        evidence.finish(reports)


def driver(monkeypatch, tmp_path, encode):
    from tests.test_native_pooling_registry import evidence_worker
    worker, hooks, _, tokens, _ = evidence_worker(monkeypatch)
    from jevlight.backends.pooled_native_runtime import PoolingNativeBase
    monkeypatch.setattr(sys.modules['vllm'], 'PoolingParams', lambda **kwargs: kwargs, raising=False)
    calls = []

    def rpc(method, args):
        calls.append(method)
        return [getattr(worker, method)(*args)]

    runtime = PoolingNativeBase()
    runtime.max_length = 1000
    runtime.task = 'token_embed'
    runtime.last_engine_forward_rows = []
    runtime.engine_forward_evidence = []
    runtime.worker_evidence_dir = tmp_path
    runtime.expected_worker_uuids = ['uuid-cuda:0']
    runtime.engine = SimpleNamespace(collective_rpc=rpc,
                                     encode=lambda *a, **k: encode(hooks[0], tokens, *a, **k))
    return runtime, calls, worker


def test_driver_reports_live_forward_and_preserves_full_native_input(monkeypatch, tmp_path):
    notified = threading.Event()
    inputs = [[4, 5, 6], [7, 8]]

    def encode(hook, tokens, rows, params, **kwargs):
        assert rows == [dict(prompt_token_ids=ids) for ids in inputs]
        assert kwargs['lora_request'] == 'unchanged-lora'
        hook(None, (), dict(input_ids=tokens), None)
        assert notified.wait(3), 'Progress must arrive while encode is blocked'
        return [SimpleNamespace(prompt_token_ids=ids) for ids in inputs]

    runtime, calls, worker = driver(monkeypatch, tmp_path, encode)
    runtime._step_progress = threading.local()
    runtime._step_progress.notify = notified.set
    assert len(runtime.pool(inputs, lora='unchanged-lora')) == 2
    assert calls == ['begin_native_step', 'finish_native_step']
    assert worker._native_step is None
    assert runtime.last_engine_forward_rows == [3]
    assert runtime.engine_forward_evidence[0]['gpu_uuid'] == 'uuid-cuda:0'
    assert runtime.last_worker_memory[0]['peak_allocated_bytes'] == 550
    assert runtime.last_worker_memory[0]['peak_reserved_bytes'] == 650
    assert len(list(tmp_path.glob('*.jsonl'))) == 1


def test_driver_preserves_original_error_and_failed_attempt_without_retry(monkeypatch, tmp_path):
    original = RuntimeError('original engine OOM')

    def encode(hook, tokens, *args, **kwargs):
        hook(None, (), dict(input_ids=tokens), None)
        raise original

    runtime, calls, worker = driver(monkeypatch, tmp_path, encode)
    with pytest.raises(RuntimeError) as caught:
        runtime.pool([[1, 2]])
    assert caught.value is original
    assert calls == ['begin_native_step', 'finish_native_step']
    assert worker._native_step is None
    assert runtime.last_engine_forward_rows == [3]
    assert 'forward_completed' in next(tmp_path.glob('*.jsonl')).read_text()
    assert runtime.last_worker_memory[0]['completed_chunks'] == 1


def test_driver_does_not_mask_engine_error_with_cleanup_error(monkeypatch, tmp_path):
    original = RuntimeError('original kernel failure')

    def encode(*args, **kwargs):
        raise original

    runtime, _, _ = driver(monkeypatch, tmp_path, encode)
    rpc = runtime.engine.collective_rpc

    def failing_rpc(method, args):
        if method == 'finish_native_step':
            raise RuntimeError('worker died during cleanup')
        return rpc(method, args)

    runtime.engine.collective_rpc = failing_rpc
    with pytest.raises(RuntimeError) as caught:
        runtime.pool([[1]])
    assert caught.value is original
    assert any('worker died' in note for note in original.__notes__)


@pytest.mark.parametrize('failure', ['no_forward', 'mapping'])
def test_driver_rejects_missing_forward_or_changed_input(monkeypatch, tmp_path, failure):
    def encode(hook, tokens, rows, *args, **kwargs):
        if failure != 'no_forward':
            hook(None, (), dict(input_ids=tokens), None)
        return [SimpleNamespace(prompt_token_ids=[999])]

    runtime, _, worker = driver(monkeypatch, tmp_path, encode)
    with pytest.raises(ValueError, match='GPU execution|mapping'):
        runtime.pool([[1]])
    assert worker._native_step is None


def test_headroom_uses_allocator_growth_and_post_forward_external_pressure(tmp_path):
    armed = journals(tmp_path, 1)
    evidence = reader(armed, tmp_path)
    forward(armed[0], memory_peak_reserved_bytes=800)
    evidence.poll()
    assert evidence.memory_summary()[0]['peak_free_lower_bound_bytes'] == 200
    forward(armed[0], chunk=2, memory_free_bytes=150, memory_reserved_bytes=700,
            memory_peak_reserved_bytes=800)
    evidence.poll()
    assert evidence.memory_summary()[0]['peak_free_lower_bound_bytes'] == 50


@pytest.mark.parametrize('field,value', [('initial_free_bytes', None),
    ('initial_reserved_bytes', -1), ('memory_total_bytes', 0)])
def test_invalid_baseline_cannot_establish_headroom(tmp_path, field, value):
    armed = journals(tmp_path, 1)
    armed[0][field] = value
    with pytest.raises(ValueError, match='baseline'):
        reader(armed, tmp_path)


@pytest.mark.parametrize('failure', ['none', 'low_second_rank', 'missing_rank', 'stale_step', 'wrong_gpu'])
def test_capacity_checks_every_current_worker_instead_of_driver_only(monkeypatch, failure):
    from types import ModuleType
    from jevlight.backends.step_batch import _try_group
    gib = 1024**3
    torch = ModuleType('torch')
    torch.cuda = SimpleNamespace(mem_get_info=lambda: (30*gib, 80*gib),
        memory_reserved=lambda: gib, reset_peak_memory_stats=lambda: None,
        synchronize=lambda: None, max_memory_allocated=lambda: gib,
        max_memory_reserved=lambda: gib, OutOfMemoryError=type('FakeOOM', (RuntimeError,), {}))
    monkeypatch.setitem(sys.modules, 'torch', torch)
    workers = [dict(rank=rank, gpu_uuid=f'GPU-u{rank}', step_id='current', completed_chunks=1,
        peak_free_lower_bound_bytes=20*gib, memory_total_bytes=80*gib,
        peak_allocated_bytes=40*gib, peak_reserved_bytes=45*gib) for rank in range(2)]
    if failure == 'low_second_rank':
        workers[1]['peak_free_lower_bound_bytes'] = 7*gib  # Below this device's 10% margin.
    elif failure == 'missing_rank':
        workers.pop()
    elif failure == 'stale_step':
        workers[1]['step_id'] = 'previous'
    elif failure == 'wrong_gpu':
        workers[1]['gpu_uuid'] = 'unrelated'
    requests = [dict(full='unchanged')]
    runtime = SimpleNamespace(emits_gpu_chunk_progress=True, expected_worker_uuids=['u0','u1'],
        last_worker_step_id='current', last_worker_memory=workers,
        last_engine_forward_rows=[1], _step_author_batch=lambda group, cap: group)
    if failure in ('missing_rank', 'stale_step', 'wrong_gpu'):
        with pytest.raises(RuntimeError, match='per-worker'):
            _try_group(runtime, requests, 1)
    else:
        result, report = _try_group(runtime, requests, 1)
        assert (result is None) == (failure == 'low_second_rank')
        assert report['status'] == ('ready' if failure == 'none' else 'insufficient_memory_margin')
        assert report['peak_reserved_mib'] == 45*1024
        assert len(report['worker_memory']) == 2
