"""CPU regression for the Valen-Decision-1.5 family; no GPU acceptance implied."""
from contextlib import nullcontext
import json
from pathlib import Path
import sys
import tomllib
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('valen-decision-1.5-0.8b', 'valen-decision-1.5-2b', 'valen-decision-1.5-4b')


def request(i):
    return {'state': {'id': i}, 'questions': {
        'phase_' + str(i): {'type': 'choice', 'instructions': 'Choose', 'criteria': {'A': 'first', 'B': 'second'}}}}


def answer(question, logits, temperature):
    return {'type': 'choice', 'choice': 'A', 'confidence': 0.2, 'probabilities': {'A': 0.6, 'B': 0.4}}


def compiled(payload, *, segments=True, keys=('A', 'B'), tokens=7):
    body = payload['request']
    index = json.loads(body['state'])['id']
    branch = SimpleNamespace(segments=[-1] * 3 + [0, 1, 1, 1] if segments else None, bbox_segments=())
    questions = [SimpleNamespace(qid=qid, keys=list(keys), kind='choice', branches=[branch], index=index)
                 for qid in body['questions']]
    return SimpleNamespace(questions=questions, logical_tokens=tokens, compute_tokens=tokens,
                           inputs={'input_ids': None}, media=[])


def author_runtime(monkeypatch, compile=compiled):
    from jevlight.backends.decision_model_service import ValenDecision15Native
    runtime = ValenDecision15Native.__new__(ValenDecision15Native)
    runtime.compiler = SimpleNamespace(compile=compile, max_length=16384)
    calls = []

    def forward(states, max_tokens):
        calls.append((len(states), max_tokens))
        return [[0] * len(state.questions) for state in states]

    runtime.model = SimpleNamespace(model_name='Valen', forward_state_batch=forward)
    package = ModuleType('types.responses')
    package.answer = answer
    monkeypatch.setitem(sys.modules, 'types.responses', package)
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(inference_mode=nullcontext))
    return runtime, calls


def test_catalog_serving_and_experiment_configs_select_the_separate_family():
    catalog = json.loads((ROOT / 'scripts/model_downloads/models.json').read_text())
    for key in KEYS:
        entry = catalog[key]
        size = key.rsplit('-', 1)[1].upper()
        assert entry['model_id'] == f'Valen-Team/Valen-Decision-1.5-{size}'
        assert len(entry['revision']) == 40 and int(entry['revision'], 16) >= 0
        serving = tomllib.loads((ROOT / 'config' / key / 'serving.toml').read_text())
        assert serving['model_id'] == entry['model_id']
        assert serving['family'] == entry['family'] == 'valen-decision-1.5'
        assert serving['weights_path'] == f'.local/models/{key}/weights'
        # The 1.5 release publishes a 16K compiler limit; Valen 1.0 keeps 32K.
        assert serving['max_length'] == 16384
        experiments = sorted((ROOT / 'config' / key).glob('*.json'))
        assert len(experiments) == 42
        assert {json.loads(path.read_text())['jev_model'] for path in experiments} == {entry['model_id']}
        entry_point = (ROOT / 'scripts/model_downloads' / key / 'download.py').read_text()
        assert f'main(default_models=["{key}"])' in entry_point
    for key in ('valen-0.8b', 'valen-2b', 'valen-4b'):
        serving = tomllib.loads((ROOT / 'config' / key / 'serving.toml').read_text())
        assert serving['family'] == 'valen' and serving['max_length'] == 32768
        assert 'family' not in catalog[key]


@pytest.mark.parametrize('family,engine,expected', [
    ('valen', 'author', 'ValenNative'), ('valen-decision-1.5', 'author', 'ValenDecision15Native'),
    ('valen', 'vllm_marker', 'ValenPoolingNative'),
    ('valen-decision-1.5', 'vllm_marker', 'ValenDecision15PoolingNative')])
def test_family_key_selects_separate_runtime_classes(monkeypatch, family, engine, expected):
    from jevlight.backends import decision_model_service as service
    built = []

    def stub(name):
        return type(name, (), {'__init__': lambda self, config: built.append(name)})

    monkeypatch.setattr(service, 'prepare_native_cache', lambda config: None)
    for name in ('ValenNative', 'ValenDecision15Native'):
        monkeypatch.setattr(service, name, stub(name))
    for module, name in (('valen_vllm_runtime', 'ValenPoolingNative'),
                         ('valen_decision15_vllm_runtime', 'ValenDecision15PoolingNative')):
        fake = ModuleType('jevlight.backends.' + module)
        setattr(fake, name, stub(name))
        monkeypatch.setitem(sys.modules, fake.__name__, fake)
    backend = service.NativeBackend(dict(model_id='test', family=family, inference_engine=engine,
                                         weights_path='weights'))
    assert built == [expected]
    assert type(backend.runtime).__name__ == expected


def test_author_runtime_is_not_the_valen_1_0_class():
    from jevlight.backends.decision_model_service import ValenDecision15Native, ValenNative
    assert not issubclass(ValenDecision15Native, ValenNative)
    assert not issubclass(ValenNative, ValenDecision15Native)
    assert ValenDecision15Native.decision_version == '1.5'
    assert ValenDecision15Native.full_attention_mask == 'bbox_blocks'


def test_author_batch_keeps_independent_question_ids_and_block_rows(monkeypatch):
    runtime, calls = author_runtime(monkeypatch)
    inputs = [request(i) for i in range(3)]
    outputs = runtime.native_batch(inputs, 2)
    assert [size for size, _ in calls] == [2, 1]
    assert [list(r['answers']) for r in outputs] == [list(r['questions']) for r in inputs]
    assert all(r['usage'] == {'input_tokens': 7, 'output_tokens': 0} for r in outputs)
    assert runtime.encode(inputs[0]) == [dict(logical_tokens=7, compute_tokens=7, max_length=16384, truncated=False)]
    with pytest.raises(ValueError, match='positive'):
        runtime.native_batch(inputs, 0)


@pytest.mark.parametrize('change,error', [
    (dict(segments=False), 'block segments'), (dict(tokens=8), 'block segments'),
    (dict(keys=('B', 'A')), 'candidate mapping')])
def test_author_runtime_rejects_incomplete_blocks_or_changed_candidates(monkeypatch, change, error):
    runtime, calls = author_runtime(monkeypatch, lambda payload: compiled(payload, **change))
    with pytest.raises(ValueError, match=error):
        runtime.encode(request(1))
    with pytest.raises(ValueError, match=error):
        runtime.native_batch([request(1)], 1)
    assert not calls


def test_author_runtime_rejects_split_or_media_states(monkeypatch):
    def split(payload):
        state = compiled(payload)
        state.inputs = None
        return state

    runtime, _ = author_runtime(monkeypatch, split)
    with pytest.raises(ValueError, match='shared-state'):
        runtime.encode(request(1))


def test_native_batch_runtime_forwards_the_whole_group_once(monkeypatch):
    from jevlight.backends.native_batch_runtime import _valen_decision15_batch
    runtime, calls = author_runtime(monkeypatch)
    runtime.compile = lambda item: compiled({'request': runtime.request(item)}, tokens=7)
    monkeypatch.setitem(sys.modules, 'types.responses', sys.modules['types.responses'])
    results = _valen_decision15_batch(runtime, [request(i) for i in range(5)], 5)
    assert calls == [(5, 32768)]
    assert [list(r['answers']) for r in results] == [['phase_' + str(i)] for i in range(5)]


def test_step_backend_lifts_author_budget_only_for_the_1_5_model(monkeypatch):
    from jevlight import step_batch_support as support
    calls = []

    def forward(states, max_tokens=32768):
        calls.append(max_tokens)
        return []

    model = SimpleNamespace(forward_state_batch=forward)
    runtime = SimpleNamespace(model=model, native_batch=lambda requests, batch_size: [])
    backend = SimpleNamespace(config={'family': 'valen-decision-1.5'}, runtime=runtime)
    support.prepare_step_backend(backend)
    wrapped = model.forward_state_batch
    support.prepare_step_backend(backend)
    assert model.forward_state_batch is wrapped
    states = [SimpleNamespace(compute_tokens=20000), SimpleNamespace(compute_tokens=100)]
    model.forward_state_batch(states)
    model.forward_state_batch([])
    assert calls == [40000, 32768]
    other = SimpleNamespace(config={'family': 'valen-decision-1.5', 'batch_linear': 'native_shape'},
                            runtime=SimpleNamespace(model=SimpleNamespace(forward_state_batch=forward)))
    with pytest.raises(ValueError, match='Valen-Decision-1.5 projection'):
        support.prepare_step_backend(other)


class GlueTokenizer:
    """Chat-turn glue as the 1.5 compiler writes it: one opener token per turn."""
    vocabulary = {'<|im_start|>': 1, '<|im_end|>': 2, 'user\n': 3, 'assistant\n': 4, '\n': 5}

    def encode(self, text, add_special_tokens=False):
        ids = []
        while text:
            token = next(t for t in self.vocabulary if text.startswith(t))
            ids.append(self.vocabulary[token])
            text = text[len(token):]
        return ids


def test_prompt_segments_mark_prefix_glue_and_the_shared_decision_block():
    from jevlight.backends.valen_decision15_blocks import COMMON, DECISION, PREFIX, glue_tokens, prompt_segments
    glue = glue_tokens(GlueTokenizer())
    assert glue == [[1, 3], [2, 5, 1, 4]]
    state = [1, 3, 9, 9, 9, 2, 5]
    ids = state + glue[0] + [7, 7, 8, 8] + glue[1] + [6, 6, 6, 6]
    assert prompt_segments(ids, glue) == (
        [PREFIX] * len(state) + [COMMON] * 2 + [DECISION] * 4 + [COMMON] * 4 + [DECISION] * 4)
    # Without the closing turns there are no block boundaries to apply.
    assert prompt_segments(state, glue) is None
    assert prompt_segments(state + glue[0] + [7], glue) is None


def test_compiled_segments_merge_decision_questions_into_one_block():
    from jevlight.backends.valen_decision15_blocks import compiled_segments
    segments = [-1, -1, 0, 1, 2, 0, 1, 2]
    branch = SimpleNamespace(segments=segments, bbox_segments=())
    state = SimpleNamespace(questions=[SimpleNamespace(branches=[branch]), SimpleNamespace(branches=[branch])])
    assert compiled_segments(state) == [-1, -1, 0, 1, 1, 0, 1, 1]
    bbox = SimpleNamespace(questions=[SimpleNamespace(branches=[SimpleNamespace(segments=segments, bbox_segments=(2,))])])
    with pytest.raises(ValueError, match='text-only block row'):
        compiled_segments(bbox)


def test_block_attention_equals_the_dense_bbox_blocks_mask():
    torch = pytest.importorskip('torch')
    from jevlight.backends.valen_decision15_blocks import block_attention
    torch.manual_seed(0)
    segments = torch.tensor([-1] * 5 + [0] * 2 + [1] * 4 + [0] * 3 + [1] * 3)
    length, heads, groups, width = len(segments), 4, 2, 8
    q = torch.randn(length, heads, width, dtype=torch.float64)
    k, v = (torch.randn(length, heads // groups, width, dtype=torch.float64) for _ in range(2))
    # Reference: prefix sees the prefix; glue and questions see prefix, glue and their own block.
    sq, sk = segments[:, None], segments[None, :]
    visible = torch.where(sq == -1, sk == -1, (sk == -1) | (sk == 0) | (sk == sq))
    expected = torch.nn.functional.scaled_dot_product_attention(
        q.transpose(0, 1), k.transpose(0, 1).repeat_interleave(groups, 0),
        v.transpose(0, 1).repeat_interleave(groups, 0), attn_mask=visible, scale=0.3).transpose(0, 1)
    assert torch.allclose(block_attention(q, k, v, segments, 0.3), expected, atol=1e-12)


def stub_pooling_worker(monkeypatch):
    sys.path.insert(0, str(ROOT / 'tests'))
    from test_native_pooling_registry import stub_engine_modules
    configs, models, _ = stub_engine_modules(monkeypatch)
    name = 'jevlight.backends.valen_decision15_pooling_worker'
    monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, name)
    import importlib
    return importlib.import_module(name), configs, models


def test_worker_registers_the_1_5_engine_and_reports_then_resets_block_rows(monkeypatch):
    module, configs, models = stub_pooling_worker(monkeypatch)
    from jevlight.backends import native_pooling_registry as registry
    assert configs['valen_qwen'] is registry.ValenDecision15Config
    assert configs['valen_qwen'] is not registry.ValenConfig
    assert models['ValenDecision15MarkerEngine'].endswith('marker_vllm_models:ValenDecision15MarkerEngine')
    assert set(registry.NATIVE_POOLING_ARCHITECTURES) == {'NativeMarkerEngine', 'ValenMarkerEngine'}
    model = SimpleNamespace(block_rows=3, causal_rows=1)
    worker = SimpleNamespace(rank=0, model_runner=SimpleNamespace(model=model))
    report = module.ValenDecision15PoolingWorker.valen_decision15_block_rows(worker)
    assert report == dict(rank=0, block_rows=3, causal_rows=1)
    assert (model.block_rows, model.causal_rows) == (0, 0)


@pytest.mark.parametrize('rows,causal,error', [(2, 0, None), (1, 0, 'block mask'), (2, 1, 'block mask')])
def test_pooling_runtime_requires_every_row_under_the_block_mask(monkeypatch, rows, causal, error):
    from jevlight.backends.valen_decision15_vllm_runtime import ValenDecision15PoolingNative
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        inference_mode=nullcontext, as_tensor=lambda value: value))
    runtime = ValenDecision15PoolingNative.__new__(ValenDecision15PoolingNative)
    calls = []
    runtime.engine = SimpleNamespace(collective_rpc=lambda name: calls.append(name) or
                                     [dict(rank=0, block_rows=rows, causal_rows=causal)])
    state = compiled({'request': {'state': '{"id": 0}', 'questions': request(0)['questions']}})
    runtime._compile = lambda item: (state, [1] * 7)
    head = SimpleNamespace(extract_features=lambda hidden, branch: SimpleNamespace(to=lambda device: hidden),
                           score_features=lambda features: features)
    runtime.model = SimpleNamespace(head=head)
    runtime.responses = SimpleNamespace(answer=answer)
    runtime.config = dict(model_id='Valen-Team/Valen-Decision-1.5-0.8B')
    hidden = SimpleNamespace(unsqueeze=lambda dim: 'hidden')
    runtime.pool = lambda ids: calls.append('pool') or [
        SimpleNamespace(outputs=SimpleNamespace(data=SimpleNamespace(ndim=2, shape=(len(row), 4), unsqueeze=hidden.unsqueeze)))
        for row in ids]
    inputs = [request(0), request(0)]
    if error:
        with pytest.raises(ValueError, match=error):
            runtime.native_batch(inputs, 2)
    else:
        assert [list(r['answers']) for r in runtime.native_batch(inputs, 2)] == [['phase_0'], ['phase_0']]
    # Counts are reset before the pool, then read for exactly this pool's rows.
    assert calls == ['valen_decision15_block_rows', 'pool', 'valen_decision15_block_rows']


BOX = {'type': 'bbox', 'bbox': [0.1, 0.2, 0.5, 0.6], 'point': [0.3, 0.4], 'confidence': 0.9}


def visual_request():
    image = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AAAA'}}
    return {'state': {'messages': [{'role': 'user', 'content': [image]}]}, 'questions': {
        'where': {'type': 'bbox', 'instructions': 'the queue'},
        'phase': {'type': 'choice', 'instructions': 'Choose', 'criteria': {'A': 'first', 'B': 'second'}}}}


def test_author_runtime_sends_image_states_and_bbox_questions_to_the_release(monkeypatch):
    import types
    runtime, calls = author_runtime(monkeypatch)
    seen = []

    def predict(payload, execution):
        seen.append((payload, execution))
        return {'model': 'Valen', 'answers': {'where': BOX, 'phase': answer(None, None, 1.0)},
                'usage': {'input_tokens': 9, 'output_tokens': 0}}

    runtime.model.predict = predict
    visual, text = visual_request(), request(1)
    assert runtime.visual(visual) and not runtime.visual(text)
    assert runtime.visual({'state': {'id': 1}, 'questions': {'where': {'type': 'bbox', 'instructions': 'x'}}})
    # A message state reaches the release unchanged; a benchmark state stays JSON text.
    assert runtime.request(visual)['state'] is visual['state']
    assert runtime.request(text)['state'] == json.dumps(text['state'])

    results = runtime.native_batch([visual, visual], 2)
    assert [r['answers']['where'] for r in results] == [BOX, BOX]
    assert len(seen) == 2 and seen[0][1] == 'shared_state' and calls == []

    prepared = []

    def local_images(payload):
        prepared.append(payload)
        return nullcontext(payload)

    def compile(payload):
        questions = [SimpleNamespace(qid=qid, keys=list(q.get('criteria', ())), kind=q['type'])
                     for qid, q in payload['request']['questions'].items()]
        return SimpleNamespace(questions=questions, logical_tokens=9, compute_tokens=9,
                               inputs={'input_ids': None}, media=['image'])

    monkeypatch.setattr(types, 'local_images', local_images, raising=False)
    runtime.compiler.compile = compile
    assert runtime.encode(visual)[0]['logical_tokens'] == 9 and prepared[0]['state'] is visual['state']


def test_decision15_validator_accepts_boxes_and_keeps_the_benchmark_checks():
    from jevlight.backends.decision_model_service import validate_decision15_answers
    visual = visual_request()
    good = {'answers': {'where': dict(BOX), 'phase': answer(None, None, 1.0)}}
    assert validate_decision15_answers(visual, good) is good
    assert validate_decision15_answers(request(1), {'answers': {'phase_1': answer(None, None, 1.0)}})
    for change in ({'bbox': [0.5, 0.2, 0.1, 0.6]}, {'bbox': [0.1, 0.2, 0.5]}, {'confidence': 1.5},
                   {'point': [0.3]}, {'type': 'choice'}, {'bbox': [0.1, 0.2, 0.5, float('nan')]}):
        bad = {'answers': {'where': dict(BOX, **change), 'phase': answer(None, None, 1.0)}}
        with pytest.raises(ValueError, match='bbox'):
            validate_decision15_answers(visual, bad)
    with pytest.raises(ValueError, match='answer IDs'):
        validate_decision15_answers(visual, {'answers': {'where': dict(BOX)}})
    unnormalized = dict(answer(None, None, 1.0), probabilities={'A': 0.6, 'B': 0.6})
    with pytest.raises(ValueError, match='normalized'):
        validate_decision15_answers(visual, {'answers': {'where': dict(BOX), 'phase': unnormalized}})


def test_pooling_runtime_rejects_image_states_and_bbox_questions():
    from jevlight.backends.valen_decision15_vllm_runtime import compile_request
    visual = visual_request()
    for payload in (visual, {'state': {'id': 1}, 'questions': {'where': visual['questions']['where']}}):
        with pytest.raises(ValueError, match='author inference engine'):
            compile_request(None, payload, None)
