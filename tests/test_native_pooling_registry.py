"""CPU regression for fresh-worker registration; no GPU acceptance implied."""
import importlib
import json
import os
import pickle
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest


def stub_engine_modules(monkeypatch):
    configs, models, constructors = {}, {}, []

    class AutoConfig:
        @staticmethod
        def register(name, cls, exist_ok=False):
            assert exist_ok
            configs[name] = cls

    class ModelRegistry:
        @staticmethod
        def register_model(name, target):
            assert isinstance(target, str)
            models[name] = target

    class Worker:
        def __init__(self, **kwargs):
            # A fresh worker must see registrations before upstream construction.
            assert set(configs) == {'qwen3_5_text', 'valen_qwen'}
            assert set(models) == {'NativeMarkerEngine', 'ValenMarkerEngine'}
            self.rank = kwargs['rank']

    def llm(**kwargs):
        constructors.append(kwargs)
        # A multiprocessing engine exposes no local driver_worker/backbone.
        return SimpleNamespace()

    modules = {
        'transformers': dict(AutoConfig=AutoConfig),
        'vllm': dict(ModelRegistry=ModelRegistry, LLM=llm),
        'vllm.config': dict(PoolerConfig=lambda **kwargs: kwargs),
        'vllm.transformers_utils.configs.qwen3_5': dict(
            Qwen3_5Config=type('Qwen3_5Config', (), {}),
            Qwen3_5TextConfig=type('Qwen3_5TextConfig', (), {})),
        'vllm.v1.worker.gpu_worker': dict(Worker=Worker),
        'torch': dict(nn=SimpleNamespace(Module=SimpleNamespace)),
    }
    for name, attrs in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    for name in ('native_pooling_registry', 'native_pooling_worker'):
        # Track the absent entry too, so imports made by a test are removed
        # when monkeypatch restores the surrounding test's real modules.
        full_name = 'jevlight.backends.' + name
        monkeypatch.setitem(sys.modules, full_name, None)
        monkeypatch.delitem(sys.modules, full_name)
        package = importlib.import_module('jevlight.backends')
        monkeypatch.setattr(package, name, None, raising=False)
        monkeypatch.delattr(package, name)
    return configs, models, constructors


def test_registration_is_lazy_repeatable_and_config_is_pickleable(monkeypatch):
    configs, models, _ = stub_engine_modules(monkeypatch)
    registry = importlib.import_module('jevlight.backends.native_pooling_registry')
    registry.register_native_pooling_models()
    registry.register_native_pooling_models()
    assert configs['valen_qwen'] is registry.ValenConfig
    assert pickle.loads(pickle.dumps(registry.ValenConfig())).__class__ is registry.ValenConfig
    assert set(models) == set(registry.NATIVE_POOLING_ARCHITECTURES)
    assert 'jevlight.backends.marker_vllm_models' not in sys.modules


@pytest.mark.parametrize('rank', [0, 1])
def test_spawned_worker_registers_without_parent_state(rank):
    # Each child starts with empty registries; CUDA/model imports are stubbed.
    code = '''
import importlib, json, os, sys
from pathlib import Path
from pytest import MonkeyPatch
sys.path.insert(0, str(Path('tests').resolve()))
from test_native_pooling_registry import stub_engine_modules
with MonkeyPatch.context() as patch:
    configs, models, _ = stub_engine_modules(patch)
    assert not configs and not models
    module = importlib.import_module('jevlight.backends.native_pooling_worker')
    worker = module.NativePoolingWorker(rank=int(sys.argv[1]))
    print(json.dumps(dict(rank=worker.rank, pid=os.getpid(), models=models,
                         config_module=configs['valen_qwen'].__module__)))
'''
    result = subprocess.run([sys.executable, '-c', code, str(rank)],
                            capture_output=True, text=True, timeout=30, check=True)
    report = json.loads(result.stdout)
    assert report['pid'] != os.getpid()
    assert report['rank'] == rank
    assert report['config_module'] == 'jevlight.backends.native_pooling_registry'
    assert report['models']['NativeMarkerEngine'].endswith(':NativeMarkerEngine')
    assert report['models']['ValenMarkerEngine'].endswith(':ValenMarkerEngine')


@pytest.mark.parametrize('architecture', ['NativeMarkerEngine', 'ValenMarkerEngine'])
def test_pooling_driver_selects_importable_worker_without_enabling_tp2(monkeypatch, tmp_path, architecture):
    _, models, constructors = stub_engine_modules(monkeypatch)
    from jevlight.backends import cuda_runtime
    from jevlight.backends.pooled_native_runtime import PoolingNativeBase
    monkeypatch.setattr('jevlight.backends.pooled_native_runtime.ROOT', tmp_path)
    monkeypatch.setattr(sys.modules['torch'], 'cuda', SimpleNamespace(
        get_device_properties=lambda device: SimpleNamespace(uuid='test-device')), raising=False)
    monkeypatch.setattr(cuda_runtime, 'prepare_cuda_device', lambda: None)
    monkeypatch.setattr(cuda_runtime, 'configure_cpu_threads', lambda **kwargs: None)
    runtime = PoolingNativeBase()
    runtime.initialize_engine(dict(max_length=1024, engine_token_budget=2048),
                              '/frozen/weights', architecture=architecture)
    args = constructors[0]
    assert architecture in models
    assert args['worker_cls'] == 'jevlight.backends.native_pooling_worker.NativePoolingWorker'
    assert args['tensor_parallel_size'] == 1
    assert args['max_model_len'] == 1024
    assert args['hf_overrides']['architectures'] == [architecture]
    assert not hasattr(runtime.model, 'backbone')


def test_worker_adapter_verification_uses_owned_model_and_preserves_error(monkeypatch, tmp_path):
    worker, _, _, _, _ = evidence_worker(monkeypatch)
    worker.parallel_config = SimpleNamespace(tensor_parallel_size=1)
    from jevlight.backends import lev_vllm_runtime
    calls = []

    def verify(model, source):
        assert model is worker.model_runner.model
        assert source == tmp_path
        calls.append(source)
        return 12

    monkeypatch.setattr(lev_vllm_runtime, 'verify_adapter', verify)
    assert worker.verify_lev_adapter(str(tmp_path)) == dict(rank=0, tensor_count=12)
    worker.parallel_config.tensor_parallel_size = 2
    with pytest.raises(ValueError, match='Sharded'):
        worker.verify_lev_adapter(str(tmp_path))
    assert calls == [tmp_path]
    worker.parallel_config.tensor_parallel_size = 1
    original = ValueError('original adapter tensor mismatch')

    def failed(*args):
        raise original

    monkeypatch.setattr(lev_vllm_runtime, 'verify_adapter', failed)
    with pytest.raises(ValueError) as caught:
        worker.verify_lev_adapter(str(tmp_path))
    assert caught.value is original


@pytest.mark.parametrize('reports', [[dict(rank=0, tensor_count=12)], [],
                                    [dict(rank=1, tensor_count=12)],
                                    [dict(rank=0, tensor_count=0)],
                                    [dict(rank=0, tensor_count=True)]])
def test_driver_requires_complete_worker_adapter_verification(reports):
    from jevlight.backends.pooled_native_runtime import PoolingNativeBase
    runtime = PoolingNativeBase()
    runtime.expected_worker_uuids = ['uuid-0']
    calls = []

    def rpc(method, args):
        calls.append((method, args))
        return reports

    runtime.engine = SimpleNamespace(collective_rpc=rpc)
    if reports == [dict(rank=0, tensor_count=12)]:
        assert runtime.verify_lev_adapter('/frozen/adapter') == 12
    else:
        with pytest.raises(ValueError, match='Incomplete'):
            runtime.verify_lev_adapter('/frozen/adapter')
    assert calls == [('verify_lev_adapter', ('/frozen/adapter',))]
    runtime.expected_worker_uuids.append('uuid-1')
    with pytest.raises(ValueError, match='Sharded'):
        runtime.verify_lev_adapter('/frozen/adapter')
    assert len(calls) == 1


def test_unknown_architecture_is_rejected_before_engine_construction(monkeypatch):
    _, _, constructors = stub_engine_modules(monkeypatch)
    from jevlight.backends import cuda_runtime
    from jevlight.backends.pooled_native_runtime import PoolingNativeBase
    monkeypatch.setattr(cuda_runtime, 'prepare_cuda_device', lambda: None)
    monkeypatch.setattr(cuda_runtime, 'configure_cpu_threads', lambda **kwargs: None)
    with pytest.raises(ValueError, match='Unqualified'):
        PoolingNativeBase().initialize_engine({}, '/frozen/weights', architecture='Other')
    assert not constructors


def evidence_worker(monkeypatch, rank=0):
    """Stub CUDA to test evidence semantics, never GPU performance/acceptance."""
    stub_engine_modules(monkeypatch)
    module = importlib.import_module('jevlight.backends.native_pooling_worker')
    worker = module.NativePoolingWorker(rank=rank)
    worker.device = f'cuda:{rank}'
    hooks, synchronized = [], []

    def register(hook, *, with_kwargs):
        assert with_kwargs
        hooks.append(hook)
        return SimpleNamespace(remove=lambda: hooks.remove(hook))

    def load_model(self, *, load_dummy_weights):
        self.model_runner = SimpleNamespace(model=SimpleNamespace(register_forward_hook=register))

    monkeypatch.setattr(module.Worker, 'load_model', load_model, raising=False)
    cuda = SimpleNamespace(
        get_device_properties=lambda device: SimpleNamespace(uuid=f'uuid-{device}'),
        synchronize=lambda device: synchronized.append(device),
        mem_get_info=lambda device: (400, 1000),
        memory_allocated=lambda device: 500,
        memory_reserved=lambda device: 600,
        reset_peak_memory_stats=lambda device: None,
        max_memory_allocated=lambda device: 550,
        max_memory_reserved=lambda device: 650)
    monkeypatch.setattr(sys.modules['torch'], 'cuda', cuda, raising=False)
    context = SimpleNamespace(attn_metadata={'layer': SimpleNamespace(
        query_start_loc=SimpleNamespace(numel=lambda: 4))})
    forward_module = ModuleType('vllm.forward_context')
    forward_module.get_forward_context = lambda: context
    monkeypatch.setitem(sys.modules, 'vllm.forward_context', forward_module)
    worker.load_model()
    tokens = SimpleNamespace(is_cuda=True, device=worker.device, numel=lambda: 99)
    return worker, hooks, synchronized, tokens, context


@pytest.mark.parametrize('rank', [0, 1])
def test_worker_forward_evidence_is_step_scoped_and_live(monkeypatch, tmp_path, rank):
    worker, hooks, synchronized, tokens, _ = evidence_worker(monkeypatch, rank)
    hooks[0](None, (), {}, None)  # No startup/profile evidence or CUDA sync.
    assert not synchronized
    armed = worker.begin_native_step('simulation-1-step-20', str(tmp_path))
    assert armed['rank'] == rank
    assert armed['pid'] == os.getpid() and armed['start_ticks'].isdigit()
    path = tmp_path / os.path.basename(armed['evidence_path'])
    assert [json.loads(line)['event'] for line in path.read_text().splitlines()] == ['armed']
    for _ in range(2):
        hooks[0](None, (), dict(input_ids=tokens), None)
    # Progress is already readable before finish RPC or encode returns.
    live = [json.loads(line) for line in path.read_text().splitlines()]
    assert [event['event'] for event in live] == ['armed', 'forward_completed', 'forward_completed']
    assert synchronized == [f'cuda:{rank}'] * 4
    with pytest.raises(ValueError, match='identity differs'):
        worker.finish_native_step('another-step')
    report = worker.finish_native_step('simulation-1-step-20')
    assert report['forwards'] == live[1:]
    assert [event['chunk'] for event in report['forwards']] == [1, 2]
    assert all(event['rows'] == 3 and event['input_tokens'] == 99 for event in report['forwards'])
    assert all(event['gpu_uuid'] == f'uuid-cuda:{rank}' for event in report['forwards'])
    assert all(event['memory_free_bytes'] == 400 and event['memory_reserved_bytes'] == 600
               for event in report['forwards'])
    worker.begin_native_step('next-step', str(tmp_path))
    assert worker.finish_native_step('next-step')['forwards'] == []
    with pytest.raises(FileExistsError):
        worker.begin_native_step('simulation-1-step-20', str(tmp_path))
    assert path.read_text().splitlines()[-1].endswith('"completed_chunks": 2}')


def test_worker_rejects_overlap_and_invalid_identity(monkeypatch, tmp_path):
    worker, _, _, _, _ = evidence_worker(monkeypatch)
    for step_id in ('', '../outside', 'bad/name', 'x' * 129):
        with pytest.raises(ValueError, match='identity'):
            worker.begin_native_step(step_id, str(tmp_path))
    with pytest.raises(ValueError, match='absolute directory'):
        worker.begin_native_step('step', 'relative')
    worker.begin_native_step('step', str(tmp_path))
    with pytest.raises(RuntimeError, match='already'):
        worker.begin_native_step('next', str(tmp_path))
    with pytest.raises(RuntimeError, match='reload'):
        worker.load_model()
    assert worker.finish_native_step('step')['forwards'] == []


@pytest.mark.parametrize('failure', ['mapping', 'cpu_input', 'wrong_device', 'cuda_error'])
def test_worker_does_not_report_failed_or_unmapped_forward(monkeypatch, tmp_path, failure):
    worker, hooks, _, tokens, context = evidence_worker(monkeypatch)
    worker.begin_native_step('step', str(tmp_path))
    if failure == 'mapping':
        context.attn_metadata = None
    elif failure == 'cpu_input':
        tokens.is_cuda = False
    elif failure == 'wrong_device':
        tokens.device = 'cuda:1'
    else:
        def cuda_failure(device):
            raise RuntimeError('original CUDA failure')
        monkeypatch.setattr(sys.modules['torch'].cuda, 'synchronize', cuda_failure)
    with pytest.raises((ValueError, RuntimeError), match='mapping|original CUDA failure'):
        hooks[0](None, (), dict(input_ids=tokens), None)
    report = worker.finish_native_step('step')
    assert report['forwards'] == []
    events = [json.loads(line)['event'] for line in open(report['evidence_path'])]
    assert events == ['armed', 'disarmed']


def test_worker_reload_replaces_hook(monkeypatch):
    worker, hooks, _, _, _ = evidence_worker(monkeypatch)
    assert len(hooks) == 1
    worker.load_model(load_dummy_weights=True)
    assert len(hooks) == 1


def test_worker_resets_own_peak_once_per_step(monkeypatch, tmp_path):
    worker, hooks, _, tokens, _ = evidence_worker(monkeypatch, rank=1)
    resets = []
    monkeypatch.setattr(sys.modules['torch'].cuda, 'reset_peak_memory_stats', resets.append)
    worker.begin_native_step('first', str(tmp_path))
    hooks[0](None, (), dict(input_ids=tokens), None)
    hooks[0](None, (), dict(input_ids=tokens), None)
    first = worker.finish_native_step('first')
    assert resets == ['cuda:1']
    assert all(event['memory_peak_allocated_bytes'] == 550 and
               event['memory_peak_reserved_bytes'] == 650 for event in first['forwards'])
    worker.begin_native_step('second', str(tmp_path))
    assert resets == ['cuda:1', 'cuda:1']
    assert worker.finish_native_step('second')['forwards'] == []


@pytest.mark.parametrize('parallel_size,qualification,lora,device_count,error', [
    (2, False, False, 2, 'qualification mode'),
    (2, True, True, 2, 'Sharded'),
    (2, True, False, 1, 'exactly'),
    (True, True, False, 2, 'positive integer'),
    (0, True, False, 2, 'positive integer'),
    (2, True, False, 2, None),
])
def test_tp_qualification_requires_explicit_scope_and_all_devices(
        monkeypatch, tmp_path, parallel_size, qualification, lora, device_count, error):
    _, _, constructors = stub_engine_modules(monkeypatch)
    from jevlight.backends import cuda_runtime
    from jevlight.backends.pooled_native_runtime import PoolingNativeBase
    monkeypatch.setattr('jevlight.backends.pooled_native_runtime.ROOT', tmp_path)
    monkeypatch.setattr(cuda_runtime, 'prepare_cuda_device', lambda: None)
    monkeypatch.setattr(cuda_runtime, 'configure_cpu_threads', lambda **kwargs: None)
    monkeypatch.setattr(sys.modules['torch'], 'cuda', SimpleNamespace(
        device_count=lambda: device_count,
        get_device_properties=lambda i: SimpleNamespace(uuid=f'uuid-{i}')), raising=False)
    if lora:
        monkeypatch.setattr('jevlight.backends.vllm_lora.install_fp32_lora_linear', lambda: None)
    config = dict(max_length=1024, engine_token_budget=2048,
                  engine_tensor_parallel_size=parallel_size,
                  native_pooling_tp_qualification=qualification)
    runtime = PoolingNativeBase()
    if error:
        with pytest.raises(ValueError, match=error):
            runtime.initialize_engine(config, '/frozen/weights', enable_lora=lora)
        assert not constructors
    else:
        runtime.initialize_engine(config, '/frozen/weights')
        assert constructors[0]['tensor_parallel_size'] == 2
        assert constructors[0]['distributed_executor_backend'] == 'mp'
        assert runtime.expected_worker_uuids == ['uuid-0', 'uuid-1']
