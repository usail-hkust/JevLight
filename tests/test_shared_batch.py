"""Concurrency/mapping regressions; these do not qualify GPU performance."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
from types import SimpleNamespace

import pytest

from jevlight.backends.shared_batch import SharedBatchBackend


class Backend:
    def __init__(self):
        self.config = {'batch_size': 196}
        self.runtime = SimpleNamespace(_step_progress=threading.local())
        self.calls = []
        self.failure = None
        self.truncate = False
        self.fail_after_progress = False

    def evaluate_batch(self, requests, capacity):
        self.calls.append((deepcopy(requests), capacity))
        if self.failure is not None:
            raise self.failure
        notify = getattr(self.runtime._step_progress, 'notify', None)
        if notify:
            notify()
        if self.fail_after_progress:
            raise RuntimeError('original GPU chunk failure')
        results = [dict(answers={'phase': {'choice': row['state']['phase']}}, usage={})
                   for row in requests]
        return results[:-1] if self.truncate else results


def inputs(simulator, size):
    return [dict(state={'id': i, 'simulator': simulator, 'phase': str(i)},
                 questions={'phase': {'type': 'choice', 'criteria': {str(i): 'complete candidate'}}})
            for i in range(size)]


def concurrent(backend, rows, capacities=None, callbacks=None):
    barrier = threading.Barrier(len(rows))
    capacities = capacities or [196] * len(rows)
    callbacks = callbacks or [None] * len(rows)

    def call(index):
        progress = backend.runtime._step_progress
        progress.notify = callbacks[index]
        barrier.wait(timeout=3)
        try:
            return backend.evaluate_batch(rows[index], capacities[index])
        finally:
            assert progress.notify is callbacks[index]

    with ThreadPoolExecutor(max_workers=len(rows)) as executor:
        futures = [executor.submit(call, i) for i in range(len(rows))]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=5))
            except Exception as error:
                outcomes.append(error)
    return outcomes


def test_whole_steps_coalesce_and_repeated_question_ids_map_back():
    native = Backend()
    backend = SharedBatchBackend(native, window_ms=100)
    rows = [inputs('ordinary', 3), inputs('cooperative', 2)]
    original = deepcopy(rows)
    outputs = concurrent(backend, rows)
    assert len(native.calls) == 1 and native.calls[0][1] == 196
    sent = native.calls[0][0]
    assert sent in [rows[0] + rows[1], rows[1] + rows[0]]
    assert rows == original
    for batch, results in zip(rows, outputs):
        assert [r['answers']['phase']['choice'] for r in results] == [r['state']['phase'] for r in batch]
        report = results[0]['usage']['shared_batch']
        assert report['steps'] == 2 and report['combined_requests'] == 5
        assert report['step_requests'] == len(batch) and report['capacity'] == 196
        assert sent[report['request_offset']:report['request_offset'] + len(batch)] == batch
    assert outputs[0][0]['usage']['shared_batch']['group_id'] == outputs[1][0]['usage']['shared_batch']['group_id']


def test_different_native_capacities_remain_separate():
    native = Backend()
    outputs = concurrent(SharedBatchBackend(native, window_ms=30),
                         [inputs('one', 2), inputs('two', 3)], capacities=[196, 99])
    assert all(isinstance(result, list) for result in outputs)
    assert sorted(capacity for _, capacity in native.calls) == [99, 196]
    assert all(result[0]['usage']['shared_batch']['steps'] == 1 for result in outputs)


def test_original_gpu_error_reaches_all_callers_once_then_queue_recovers():
    native = Backend()
    native.failure = RuntimeError('original CUDA OOM with complete input')
    backend = SharedBatchBackend(native, window_ms=100)
    outcomes = concurrent(backend, [inputs('one', 2), inputs('two', 2)])
    assert all(outcome is native.failure for outcome in outcomes)
    assert len(native.calls) == 1
    native.failure = None
    assert len(backend.evaluate_batch(inputs('next', 2), 196)) == 2


def test_missing_native_results_fail_every_step_without_partial_return():
    native = Backend()
    native.truncate = True
    outcomes = concurrent(SharedBatchBackend(native, window_ms=100),
                          [inputs('one', 2), inputs('two', 2)])
    assert all(isinstance(outcome, ValueError) and 'count mismatch' in str(outcome) for outcome in outcomes)


def test_real_chunk_callback_fans_out_and_disconnected_client_is_isolated():
    native = Backend()
    callbacks = []

    def broken():
        callbacks.append('broken')
        raise BrokenPipeError('client disconnected')

    def healthy():
        callbacks.append('healthy')

    outcomes = concurrent(SharedBatchBackend(native, window_ms=100),
                          [inputs('one', 2), inputs('two', 2)], callbacks=[broken, healthy])
    assert all(isinstance(outcome, list) for outcome in outcomes)
    assert sorted(callbacks) == ['broken', 'healthy']


def test_single_simulator_does_not_wait_for_a_second_or_emit_fake_progress():
    native = Backend()
    callbacks = []
    native.runtime._step_progress.notify = lambda: callbacks.append('chunk')
    backend = SharedBatchBackend(native, window_ms=1)
    assert backend.evaluate_batch([], 196) == [] and not native.calls
    assert len(backend.evaluate_batch(inputs('alone', 3), 196)) == 3
    assert callbacks == ['chunk'] and len(native.calls) == 1


def test_more_callers_than_group_limit_all_finish_with_whole_steps():
    native = Backend()
    outcomes = concurrent(SharedBatchBackend(native, window_ms=30, max_steps=2),
                          [inputs(str(i), 2) for i in range(7)])
    assert all(isinstance(result, list) and len(result) == 2 for result in outcomes)
    assert sum(len(rows) for rows, _ in native.calls) == 14
    assert all(len(rows) in (2, 4) for rows, _ in native.calls)


@pytest.mark.parametrize('options', [dict(window_ms=0), dict(window_ms=-1),
    dict(window_ms=float('nan')), dict(window_ms=float('inf')), dict(window_ms=True),
    dict(window_ms=1, max_steps=1), dict(window_ms=1, max_steps=2.5)])
def test_invalid_deployment_options_fail(options):
    with pytest.raises(ValueError):
        SharedBatchBackend(Backend(), **options)


@pytest.mark.parametrize('capacity', [0, -1, 197, 1.5, True])
def test_invalid_capacity_never_enters_queue(capacity):
    native = Backend()
    with pytest.raises(ValueError):
        SharedBatchBackend(native, window_ms=1).evaluate_batch(inputs('invalid', 2), capacity)
    assert not native.calls


@pytest.mark.parametrize('failure', [False, True])
def test_http_streaming_integration_keeps_mapping_and_backend_errors(monkeypatch, failure):
    import requests
    from jevlight import step_batch_support
    native = Backend()
    native.config['shared_batch_window_ms'] = 0
    native.fail_after_progress = failure
    monkeypatch.setattr(step_batch_support, 'prepare_step_backend', lambda backend: None)
    server = step_batch_support.make_step_server(native, '127.0.0.1', 0, 'cpu-test')
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
    thread.start()
    barrier = threading.Barrier(2)

    def call(index):
        barrier.wait(timeout=3)
        with requests.post(f'http://127.0.0.1:{server.server_port}/v1/systemone/batch',
                           json=dict(requests=inputs(str(index), index+2), batch_size=196),
                           timeout=3) as response:
            assert response.headers['Transfer-Encoding'] == 'chunked'
            return response.json()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(call, i) for i in range(2)]
            payloads = [f.result(timeout=5) for f in futures]
        assert len(native.calls) == 2
        if failure:
            assert all(payload['error']['http_status'] == 502 for payload in payloads)
            assert all('original GPU chunk failure' in payload['error']['message'] for payload in payloads)
        else:
            assert [len(payload['results']) for payload in payloads] == [2, 3]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_scheduler_report_is_saved_with_raw_failure(tmp_path):
    import json
    native = Backend()
    native.log_path = tmp_path / 'requests.jsonl'
    native.failure = RuntimeError('original failed engine attempt')
    backend = SharedBatchBackend(native, window_ms=1)
    with pytest.raises(RuntimeError, match='original failed engine attempt'):
        backend.evaluate_batch(inputs('one', 2), 196)
    event = json.loads((tmp_path / 'requests_shared_batch.jsonl').read_text())
    assert event['status'] == 'failed'
    assert event['error'] == 'RuntimeError: original failed engine attempt'
    assert event['combined_requests'] == 2


@pytest.mark.parametrize('entrypoint', ['server', 'backend', 'engine_selection'])
def test_unsafe_coalescing_rejected_before_runtime_preparation(monkeypatch, entrypoint):
    from jevlight import step_batch_support
    from jevlight.backends import decision_model_service
    from scripts.experiments.serve_decision_model import build_backend

    monkeypatch.setattr(step_batch_support, 'prepare_step_backend',
                        lambda *a: pytest.fail('runtime prepared before safety gate'))
    monkeypatch.setattr(decision_model_service, 'NativeBackend',
                        lambda *a: pytest.fail('GPU model loaded before safety gate'))
    native = Backend()
    native.config['shared_batch_window_ms'] = 100
    with pytest.raises(ValueError, match='failures are not isolated'):
        if entrypoint == 'server':
            step_batch_support.make_step_server(native, '127.0.0.1', 0, 'cpu-test')
        else:
            build_backend(native.config, selection={} if entrypoint == 'engine_selection' else None)


@pytest.mark.parametrize('failure_stage', ['encoding', 'native_validation', 'answer_validation'])
def test_shared_http_service_isolates_bad_simulation_without_retry(monkeypatch, failure_stage):
    """Use the production NativeBackend lock/encoding/validation path, no GPU."""
    import requests
    from jevlight import step_batch_support
    from jevlight.backends.decision_model_service import NativeBackend

    original_error = ValueError(f'bad simulation: original {failure_stage} error')
    encoded, gpu_calls, validated = [], [], []

    def encode(row):
        encoded.append(deepcopy(row))
        if failure_stage == 'encoding' and row['state']['simulator'] == 'bad':
            raise original_error
        return [{'encoded_tokens': 17, 'truncated': False}]

    def native_batch(rows, capacity):
        gpu_calls.append((deepcopy(rows), capacity))
        if failure_stage == 'native_validation' and rows[0]['state']['simulator'] == 'bad':
            raise original_error
        callback = getattr(native.runtime._step_progress, 'notify', None)
        if callback:
            callback()
        return [dict(answers={'phase': {'choice': row['state']['phase']}}, usage={}) for row in rows]

    def validate(row, result):
        validated.append(deepcopy(row))
        if failure_stage == 'answer_validation' and row['state']['simulator'] == 'bad':
            raise original_error
        return result

    native = NativeBackend.__new__(NativeBackend)
    native.config = {'batch_size': 196}  # Absent window uses the production default 0.
    native.lock = threading.Lock()
    native.log_path = None
    native.runtime = SimpleNamespace(encode=encode, native_batch=native_batch,
                                     _step_progress=threading.local())
    native.answer_validator = validate
    monkeypatch.setattr(step_batch_support, 'prepare_step_backend', lambda backend: None)
    server = step_batch_support.make_step_server(native, '127.0.0.1', 0, 'cpu-test')
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
    thread.start()
    rows = [inputs('good', 3), inputs('bad', 2)]
    original = deepcopy(rows)
    barrier = threading.Barrier(2)

    def call(index):
        barrier.wait(timeout=3)
        with requests.post(f'http://127.0.0.1:{server.server_port}/v1/systemone/batch',
                           json=dict(requests=rows[index], batch_size=196), timeout=3) as response:
            return response.json()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(call, i) for i in range(2)]
            good, bad = [future.result(timeout=5) for future in futures]
        assert rows == original
        assert [r['answers']['phase']['choice'] for r in good['results']] == ['0', '1', '2']
        assert 'results' not in bad and bad['error']['http_status'] == 502
        assert str(original_error) in bad['error']['message']
        assert sum(row['state']['simulator'] == 'good' for row in encoded) == 3
        assert sum(row['state']['simulator'] == 'bad' for row in encoded) == (1 if failure_stage == 'encoding' else 2)
        assert [batch for batch, _ in gpu_calls if batch[0]['state']['simulator'] == 'good'] == [rows[0]]
        assert len(gpu_calls) == (1 if failure_stage == 'encoding' else 2)
        assert all(capacity == 196 and batch in rows for batch, capacity in gpu_calls)
        assert sum(row['state']['simulator'] == 'good' for row in validated) == 3
        assert all('shared_batch' not in result['usage'] for result in good['results'])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()
