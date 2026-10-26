"""Identity preflight must distinguish aliases, loaded assets and missing evidence."""
import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from jevlight import service_identity as identity


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    weights = tmp_path / 'weights'
    weights.mkdir()
    (weights / 'head.pt').write_bytes(b'original head')
    manifest = dict(status='downloaded', model_id='native/test', revision='pinned', bases=[],
                    files=[dict(path='head.pt', size=13,
                                sha256=hashlib.sha256(b'original head').hexdigest())])
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'jevlight').mkdir()
    (tmp_path / 'jevlight/model.py').write_text('# original native implementation\n')
    scripts = tmp_path / 'scripts'
    (scripts / 'model_downloads').mkdir(parents=True)
    (scripts / 'model_downloads/runtime_sources.json').write_text(json.dumps(
        {'native': dict(path='author', revision='pinned')}))
    (scripts / 'experiments').mkdir()
    (scripts / 'experiments/serve_decision_model.py').write_text('# service\n')
    (tmp_path / 'author').mkdir()
    monkeypatch.setattr(identity.subprocess, 'check_output',
                        lambda args, **kwargs: '' if 'status' in args else 'pinned\n')
    return tmp_path, dict(weights_path='weights', model_id='native/test', family='native')


def test_capture_is_stable_and_does_not_expose_config_credentials(snapshot):
    root, config = snapshot
    config['api_key'] = 'private-test-value'
    first = identity.capture_identity(root, config)
    config.update(host='elsewhere', port=9999)
    assert first == identity.capture_identity(root, config)
    assert 'private-test-value' not in json.dumps(first)
    config['engine_tensor_parallel_size'] = 2
    assert first != identity.capture_identity(root, config)


@pytest.mark.parametrize('change', ['head', 'size', 'digest', 'status', 'model', 'revision', 'missing'])
def test_incomplete_or_changed_assets_fail_closed(snapshot, change):
    root, config = snapshot
    path = root / 'manifest.json'
    manifest = json.loads(path.read_text())
    if change == 'head':
        (root / 'weights/head.pt').write_bytes(b'modified head')
    elif change == 'size':
        manifest['files'][0]['size'] = 99
    elif change == 'digest':
        manifest['files'][0]['sha256'] = 'unknown'
    elif change == 'status':
        manifest['status'] = 'downloading'
    elif change == 'model':
        manifest['model_id'] = 'another/alias'
    elif change == 'revision':
        manifest.pop('revision')
    else:
        (root / 'weights/head.pt').unlink()
    path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        identity.capture_identity(root, config)


def test_code_and_base_identity_are_required(snapshot):
    root, config = snapshot
    first = identity.capture_identity(root, config)
    (root / 'jevlight/model.py').write_text('# changed implementation\n')
    assert first != identity.capture_identity(root, config)
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['bases'] = [dict(weights_path='missing-base', model_id='base', revision='pinned')]
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(FileNotFoundError):
        identity.capture_identity(root, config)


def test_base_manifest_inside_snapshot_is_included(snapshot):
    root, config = snapshot
    base = root / 'base'
    base.mkdir()
    content = b'base weights'
    (base / 'model.bin').write_bytes(content)
    manifest = dict(status='downloaded', model_id='native/base', revision='base-rev',
                    files=[dict(path='model.bin', size=len(content),
                                sha256=hashlib.sha256(content).hexdigest())])
    (base / 'manifest.json').write_text(json.dumps(manifest))
    primary_path = root / 'manifest.json'
    primary = json.loads(primary_path.read_text())
    primary['bases'] = [dict(model_id='native/base', revision='base-rev', weights_path='base')]
    primary_path.write_text(json.dumps(primary))
    assert identity.capture_identity(root, config)['bases'][0]['revision'] == 'base-rev'
    primary['bases'][0]['revision'] = 'wrong-rev'
    primary_path.write_text(json.dumps(primary))
    with pytest.raises(ValueError, match='matching downloaded'):
        identity.capture_identity(root, config)


def test_changed_identity_during_loading_is_not_served(snapshot, monkeypatch):
    import sys
    from scripts.experiments import serve_decision_model as serving
    root, config = snapshot
    config_path = root / 'serving.toml'
    config_path.write_text('model_id="native/test"\nfamily="native"\nweights_path="weights"\n')
    monkeypatch.setattr(serving, 'ROOT', root)
    monkeypatch.setattr(sys, 'argv', ['serve', '--config', str(config_path),
                        '--request-log', str(root / 'results/requests.jsonl'), '--checkpoint-identity'])
    def build(*args, **kwargs):
        (root / 'jevlight/model.py').write_text('# code changed while loading\n')
        return SimpleNamespace()
    monkeypatch.setattr(serving, 'build_backend', build)
    with pytest.raises(ValueError, match='changed during model loading'):
        serving.main()


def test_unpinned_or_dirty_author_runtime_is_rejected(snapshot, monkeypatch):
    root, config = snapshot
    monkeypatch.setattr(identity.subprocess, 'check_output', lambda *args, **kwargs: 'changed')
    with pytest.raises(ValueError, match='author source'):
        identity.capture_identity(root, config)


def test_bundled_author_code_is_verified_from_weight_manifest(snapshot):
    root, config = snapshot
    config['family'] = 'bundled'
    with pytest.raises(ValueError, match='author source'):
        identity.capture_identity(root, config)
    path = root / 'weights/native_head.py'
    path.write_bytes(b'# pinned author head\n')
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['files'].append(dict(path=path.name, size=path.stat().st_size,
                                 sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest_path.write_text(json.dumps(manifest))
    captured = identity.capture_identity(root, config)
    assert captured['author']['source'] == 'weight_snapshot'
    path.write_bytes(b'# changed author head\n')
    with pytest.raises(ValueError, match='inventory|content differs'):
        identity.capture_identity(root, config)


def test_same_size_large_shard_change_updates_identity_without_rehash(snapshot, monkeypatch):
    root, config = snapshot
    shard = root / 'weights/model.safetensors'
    with shard.open('wb') as stream:
        stream.truncate(33 * 1024**2)
    path = root / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['files'].append(dict(path=shard.name, size=shard.stat().st_size, sha256='a' * 64))
    path.write_text(json.dumps(manifest))
    digest = identity._digest
    def small_only(path):
        assert Path(path) != shard, 'Large shard was redundantly hashed'
        return digest(path)
    monkeypatch.setattr(identity, '_digest', small_only)
    first = identity.capture_identity(root, config)
    before = shard.stat()
    with shard.open('r+b') as stream:
        stream.write(b'updated shard')
    # Some shared filesystems coarsen timestamps for writes within one tick.
    # This checks stat-based invalidation, not a full large-shard rehash.
    import os
    os.utime(shard, ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000))
    assert first != identity.capture_identity(root, config)
    assert first['weight_verification'] == 'manifest_and_stat_large_shards_rehash_small_files'


@pytest.mark.parametrize('qualified', [False, True])
def test_http_probe_requires_real_identity_not_health_alias(snapshot, monkeypatch, qualified):
    import requests
    from jevlight import step_batch_support
    root, config = snapshot
    backend = SimpleNamespace(config=config, runtime=SimpleNamespace(expected_worker_uuids=['test-gpu']))
    monkeypatch.setattr(step_batch_support, 'prepare_step_backend', lambda backend: None)
    if qualified:
        backend.service_identity = identity.service_document(identity.capture_identity(root, config), backend)
    server = step_batch_support.make_step_server(backend, '127.0.0.1', 0, 'native/test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        if qualified:
            result = identity.probe_service_identity(url, model='native/test', timeout=2)
            assert result == backend.service_identity
            assert result['qualification'] == 'identity_only_resume_unverified'
            with pytest.raises(ValueError, match='mismatched'):
                identity.probe_service_identity(url, model='wrong/alias', timeout=2)
            backend.service_identity['fingerprint'] = 'tampered'
            with pytest.raises(ValueError, match='mismatched'):
                identity.probe_service_identity(url, model='native/test', timeout=2)
        else:
            with pytest.raises(requests.HTTPError, match='503'):
                identity.probe_service_identity(url, model='native/test', timeout=2)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize('change', ['instance', 'fingerprint', 'unqualified'])
def test_pinned_batch_rejects_replacement_before_inference(snapshot, monkeypatch, change):
    from jevlight import step_batch_support
    root, config = snapshot
    calls = []
    backend = SimpleNamespace(config=config, runtime=SimpleNamespace(
        expected_worker_uuids=['test-gpu'], _step_progress=threading.local()),
        evaluate_batch=lambda *args: calls.append(args))
    monkeypatch.setattr(step_batch_support, 'prepare_step_backend', lambda backend: None)
    document = identity.service_document(identity.capture_identity(root, config), backend)
    backend.service_identity = dict(document)
    if change == 'unqualified':
        del backend.service_identity
    elif change == 'instance':
        backend.service_identity['instance_id'] = 'replacement'
    else:
        backend.service_identity['fingerprint'] = 'different-weights'
    server = step_batch_support.make_step_server(backend, '127.0.0.1', 0, 'native/test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = step_batch_support.StepBatchClient(transport='local',
        base_url=f'http://127.0.0.1:{server.server_port}', model='native/test',
        batch_size=196, timeout=2, max_retries=0)
    client.expected_service_identity = document
    try:
        results = client.evaluate_batch([dict(state={}, questions={})])
        assert results[0].http_status == 409
        assert 'instance or identity changed' in results[0].error
        assert calls == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_resume_identity_allows_restart_but_retains_loaded_assets(snapshot):
    root, config = snapshot
    backend = SimpleNamespace(runtime=SimpleNamespace(expected_worker_uuids=['test-gpu']))
    first = identity.service_document(identity.capture_identity(root, config), backend)
    second = identity.service_document(identity.capture_identity(root, config), backend)
    assert first['instance_id'] != second['instance_id']
    assert identity.resume_identity(first) == identity.resume_identity(second)
    config['engine_tensor_parallel_size'] = 2
    changed = identity.service_document(identity.capture_identity(root, config), backend)
    assert identity.resume_identity(first) != identity.resume_identity(changed)
