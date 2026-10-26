"""A downloaded status cannot hide omitted files or a conflicting checkpoint."""
import json

import pytest

from scripts.model_downloads import download
from scripts.model_downloads.verify_snapshots import validate_coverage


def test_manifest_must_cover_every_selected_file(tmp_path):
    metadata = dict(id='author/model', sha='frozen', siblings=[
        dict(rfilename='readout.safetensors'), dict(rfilename='config.json')])
    snapshot = dict(model_id='author/model', revision='frozen', weights_path=str(tmp_path),
                    files=[dict(path='config.json')])
    with pytest.raises(ValueError, match='complete selected repository'):
        validate_coverage(snapshot, metadata, 'model')
    snapshot['files'].append(dict(path='readout.safetensors'))
    validate_coverage(snapshot, metadata, 'model')
    snapshot['files'].append(dict(path='readout.safetensors'))
    with pytest.raises(ValueError, match='complete selected repository'):
        validate_coverage(snapshot, metadata, 'model')


def test_indexed_missing_weight_is_rejected(tmp_path):
    index = 'model.safetensors.index.json'
    (tmp_path / index).write_text(json.dumps({'weight_map': {'layer.weight': 'missing.safetensors'}}))
    metadata = dict(id='author/model', sha='frozen', siblings=[dict(rfilename=index)])
    snapshot = dict(model_id='author/model', revision='frozen', weights_path=str(tmp_path),
                    files=[dict(path=index)])
    with pytest.raises(ValueError, match='Missing indexed weight shard'):
        validate_coverage(snapshot, metadata, 'model')


def test_download_does_not_silently_reuse_a_different_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(download, 'ROOT', tmp_path)
    directory = tmp_path / '.local/models/model'
    directory.mkdir(parents=True)
    manifest = directory / 'manifest.json'
    content = json.dumps(dict(model_id='author/model', revision='old'))
    manifest.write_text(content)
    with pytest.raises(ValueError, match='requested frozen identity'):
        download.snapshot('model', 'author/model', 'new')
    assert manifest.read_text() == content
