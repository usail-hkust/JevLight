"""Opt-in identity evidence for a locally loaded native service.

Large weights reuse the downloaded manifest's digest plus local file identity;
this is deliberately not a fresh integrity audit or resume qualification.
"""
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import uuid


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _snapshot(weights, *, expected_model=None, expected_revision=None):
    weights = Path(weights).resolve(strict=True)
    manifest_path = weights / 'manifest.json'
    if not manifest_path.is_file():
        manifest_path = weights.parent / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get('status') != 'downloaded' or not manifest.get('revision')
            or not manifest.get('files')
            or (expected_model and manifest.get('model_id') != expected_model)
            or (expected_revision and manifest['revision'] != expected_revision)):
        raise ValueError('Service identity requires a matching downloaded weight manifest')
    inventory = {}
    for entry in manifest['files']:
        name = entry['path']
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Invalid weight inventory path')
        path = (weights / name).resolve(strict=True)
        if not path.is_relative_to(weights) or name in inventory:
            raise ValueError('Invalid or duplicate weight inventory path')
        stat = path.stat()
        digest = entry.get('sha256', '')
        if (not path.is_file() or stat.st_size != entry['size']
                or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError(f'Invalid weight inventory: {name}')
        # Heads, calibration and tokenizers are rehashed; multi-GB shards are
        # represented by their previously verified digest and current stat.
        if stat.st_size <= 32 * 1024**2 and _digest(path) != digest:
            raise ValueError(f'Weight content differs from manifest: {name}')
        inventory[name] = dict(sha256=digest, size=stat.st_size, device=stat.st_dev,
                               inode=stat.st_ino, mtime_ns=stat.st_mtime_ns,
                               ctime_ns=stat.st_ctime_ns)
    return dict(model_id=manifest['model_id'], revision=manifest['revision'],
                manifest_sha256=_digest(manifest_path), inventory=fingerprint(inventory)), manifest


def capture_identity(root, config, *, execution=None):
    """Capture before/after loading; reject missing identities, never guess them."""
    root = Path(root).resolve()
    primary, manifest = _snapshot(root / config['weights_path'], expected_model=config['model_id'])
    bases = []
    for base in manifest.get('bases', []):
        identity, _ = _snapshot(root / base['weights_path'], expected_model=base['model_id'],
                                expected_revision=base['revision'])
        bases.append(identity)
    sources_path = root / 'scripts/model_downloads/runtime_sources.json'
    sources = json.loads(sources_path.read_text())
    family = config['family']
    if family in sources:
        source = sources[family]
        directory = root / source['path']
        if not directory.is_dir():
            raise ValueError(f'Service identity author source is missing: {family}')
        revision = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(directory), 'status', '--porcelain',
                                         '--untracked-files=no'], text=True)
        if revision != source['revision'] or dirty:
            raise ValueError('Service identity author source differs from pinned revision')
        author = dict(family=family, revision=revision, source='pinned_repository')
    else:
        bundled = [f['path'] for f in manifest['files'] if f['path'].endswith('.py')]
        if not bundled:
            raise ValueError(f'Service identity author source is not qualified: {family}')
        author = dict(family=family, revision=manifest['revision'], source='weight_snapshot',
                      files=bundled)
    files = sorted((root / 'jevlight').rglob('*.py'))
    files += [root / 'scripts/experiments/serve_decision_model.py', sources_path]
    versions = {}
    for package in ('torch', 'vllm', 'transformers', 'numpy', 'safetensors'):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    # Never expose arbitrary serving config values or credentials in the API.
    # Host/port are routing, not loaded-model identity.
    semantic_config = {k: v for k, v in config.items() if k not in ('host', 'port')}
    return dict(schema=1, model_id=config['model_id'], weights=primary, bases=bases,
                author=author,
                config_sha256=fingerprint(semantic_config), execution=execution or {},
                code_sha256=fingerprint({str(p.relative_to(root)): _digest(p) for p in files}),
                runtime=dict(python=platform.python_version(), packages=versions),
                weight_verification='manifest_and_stat_large_shards_rehash_small_files')


def service_document(identity, backend):
    runtime = backend.runtime
    loaded = dict(identity, backend_class=f'{type(backend).__module__}.{type(backend).__qualname__}',
                  runtime_class=f'{type(runtime).__module__}.{type(runtime).__qualname__}',
                  worker_gpu_uuids=list(getattr(runtime, 'expected_worker_uuids', [])))
    return dict(schema=1, qualification='identity_only_resume_unverified',
                fingerprint=fingerprint(loaded), identity=loaded,
                instance_id=uuid.uuid4().hex, pid=os.getpid())


def probe_service_identity(base_url, *, model, timeout, api_key=None):
    """One explicit preflight request; no hidden retry or inference fallback."""
    import requests
    headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
    with requests.get(base_url.rstrip('/') + '/v1/service-identity', headers=headers,
                      timeout=timeout) as response:
        response.raise_for_status()
        document = response.json()
    if (document.get('schema') != 1 or not document.get('instance_id')
            or document.get('identity', {}).get('model_id') != model
            or document.get('fingerprint') != fingerprint(document.get('identity'))):
        raise ValueError('Invalid or mismatched native service identity')
    return document


def resume_identity(document):
    """Persist loaded assets; each new segment pins its freshly probed instance.

    A service restart with identical weights/code/runtime is allowed between
    segments. Replacement during a segment is rejected by the batch endpoint.
    """
    return {key: document[key] for key in ('schema', 'fingerprint', 'identity')}
