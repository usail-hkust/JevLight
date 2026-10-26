"""Complete independent rows and native candidate order survive author adapters."""
from collections import OrderedDict
from copy import deepcopy
from types import SimpleNamespace

import pytest

from jevlight.backends.structured_decision import D3Native, PplxDeciderNative, validate_mapping


def request(value, order=('ETWT', 'NTST', 'ELWL', 'NLSL')):
    return {'state': {'intersection_id': value, 'waiting': value},
            'questions': {'phase': {'type': 'choice',
                                   'criteria': OrderedDict((k, k + ' full description') for k in order)}}}


def test_d3_submits_all_independent_junction_rows_in_one_call():
    calls = []
    requests = [request(11), request(23, ('NLSL', 'ELWL', 'ETWT', 'NTST'))]
    original = deepcopy(requests)
    runtime = D3Native.__new__(D3Native)
    def prepare(state, questions):
        return SimpleNamespace(errors={}, keys=['phase'], runnable=['phase'],
            questions={'phase': SimpleNamespace(keys=list(questions['phase']['criteria']))},
            sequences={'phase': [state['intersection_id'], 99]})
    def probabilities(sequences, counts):
        calls.append((sequences, counts))
        return [[.1, .7, .1, .1], [.7, .1, .1, .1]]
    def respond(item, rows, tokens):
        keys = item.questions['phase'].keys
        values = rows['phase']
        return {'answers': {'phase': {'type': 'choice',
            'choice': keys[max(range(4), key=values.__getitem__)],
            'probabilities': dict(zip(keys, values))}}, 'usage': {'input_tokens': tokens}}
    runtime.engine = SimpleNamespace(prepare=prepare, probabilities=probabilities, respond=respond)
    result = runtime.native_batch(requests, 196)
    assert calls == [([[11, 99], [23, 99]], [4, 4])]
    assert [r['answers']['phase']['choice'] for r in result] == ['NTST', 'NLSL']
    assert requests == original


def test_partial_or_error_author_output_is_rejected():
    source = request(3)
    for result in ({'answers': {}}, {'answers': {'phase': {'error': 'max_length_exceeded'}}},
                   {'answers': {'phase': {'type': 'choice', 'choice': 'invalid'}}}):
        with pytest.raises(ValueError):
            validate_mapping(source, result)


def test_mapping_check_does_not_add_probability_acceptance():
    source = request(3)
    result = {'answers': {'phase': {'type': 'choice', 'choice': 'ETWT',
        'probabilities': {k: .123 for k in source['questions']['phase']['criteria']}}}}
    assert validate_mapping(source, result) is result
    result['answers']['phase']['probabilities'] = dict(reversed(list(
        result['answers']['phase']['probabilities'].items())))
    with pytest.raises(ValueError, match='mapping or order'):
        validate_mapping(source, result)


def test_d3_rejects_truncation_before_inference():
    runtime = D3Native.__new__(D3Native)
    runtime.engine = SimpleNamespace(prepare=lambda *args: SimpleNamespace(
        errors={'phase': {'error': 'max_length_exceeded'}}))
    with pytest.raises(ValueError, match='max_length_exceeded'):
        runtime.native_batch([request(1)], 196)


@pytest.mark.parametrize('fail', [False, True])
def test_joint_requests_stay_independent_and_gpu_hook_is_removed(monkeypatch, fail):
    import sys
    calls, removed = [], []
    runtime = PplxDeciderNative.__new__(PplxDeciderNative)
    runtime.packed = None
    runtime.max_length = 100
    requests = [request(11), request(23, ('NLSL', 'ELWL', 'ETWT', 'NTST'))]
    originals = deepcopy(requests)
    def encode(source):
        return SimpleNamespace(keys=list(source['questions']), length=source['state']['waiting'],
                               source=source, markers=[5])
    def register(hook):
        calls.append(hook)
        return SimpleNamespace(remove=lambda: removed.append(True))
    def forward(chunks):
        assert [c.source for c in chunks] == requests
        assert len(calls) == 1
        calls[0](None, (), SimpleNamespace(is_cuda=not fail, shape=(2, 255)))
        return [[[1, 2, 3, 4]], [[4, 3, 2, 1]]]
    def respond(source, rows, chunks, temperature):
        assert chunks[0].source is source and temperature == 1.23
        keys = list(source['questions']['phase']['criteria'])
        values = rows['phase']
        return {'answers': {'phase': dict(type='choice', choice=keys[values.index(max(values))],
                                         probabilities=dict(zip(keys, values)))}}
    runtime.engine = SimpleNamespace(encoder=SimpleNamespace(validate=lambda _: None, encode=encode),
        readout=SimpleNamespace(register_forward_hook=register), reference_logits=forward,
        _respond=respond, temperature=1.23)
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(is_tensor=lambda _: True))
    if fail:
        with pytest.raises(RuntimeError, match='CUDA'):
            runtime.native_batch(requests, 196)
        assert runtime.last_engine_forward_rows == []
    else:
        result = runtime.native_batch(requests, 196)
        assert [r['answers']['phase']['choice'] for r in result] == ['NLSL', 'NLSL']
        assert runtime.last_engine_forward_rows == [2]
    assert removed == [True]
    assert requests == originals


def test_joint_request_overflow_is_rejected_without_splitting_questions():
    runtime = PplxDeciderNative.__new__(PplxDeciderNative)
    runtime.max_length = 10
    runtime.engine = SimpleNamespace(encoder=SimpleNamespace(validate=lambda _: None,
        encode=lambda _: SimpleNamespace(length=11, keys=['phase'])))
    with pytest.raises(ValueError, match='Complete joint request needs 11 tokens'):
        runtime.prepared(request(1))
