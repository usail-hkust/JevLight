"""Device identity must survive UUID conversion for one or multiple workers."""
import os
import sys
from types import SimpleNamespace

import pytest

from jevlight.backends import cuda_runtime


def setup_cuda(monkeypatch, visible, actual, *, initialized=False):
    calls = []
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES', visible)
    monkeypatch.delenv('LD_LIBRARY_PATH', raising=False)

    def properties(index):
        calls.append((index, os.environ['CUDA_VISIBLE_DEVICES']))
        return SimpleNamespace(uuid=actual[index])

    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        version=SimpleNamespace(cuda='12.8'), cuda=SimpleNamespace(
            is_initialized=lambda: initialized, get_device_properties=properties)))
    monkeypatch.setattr(cuda_runtime.subprocess, 'check_output',
                        lambda *args, **kwargs: '0, GPU-alpha\n1, GPU-beta\n')
    return calls


@pytest.mark.parametrize('visible,actual,expected', [
    ('GPU-alpha', ['alpha'], '0'),
    ('GPU-beta,GPU-alpha', ['beta', 'alpha'], '1,0'),
    (' GPU-alpha , GPU-beta ', ['GPU-alpha', 'GPU-beta'], '0,1'),
])
def test_uuid_selection_preserves_logical_order(monkeypatch, visible, actual, expected):
    calls = setup_cuda(monkeypatch, visible, actual)
    cuda_runtime.prepare_cuda_device()
    assert os.environ['CUDA_VISIBLE_DEVICES'] == expected
    assert calls == [(i, expected) for i in range(len(actual))]


@pytest.mark.parametrize('visible,message', [
    ('GPU-alpha,GPU-alpha', 'distinct'),
    ('GPU-alpha,1', 'mixture'),
    ('0,GPU-beta', 'mixture'),
    ('GPU-missing', 'not present'),
])
def test_invalid_uuid_selection_fails_before_cuda(monkeypatch, visible, message):
    calls = setup_cuda(monkeypatch, visible, [])
    with pytest.raises(ValueError, match=message):
        cuda_runtime.prepare_cuda_device()
    assert not calls
    assert os.environ['CUDA_VISIBLE_DEVICES'] == visible


def test_every_selected_device_identity_is_verified(monkeypatch):
    setup_cuda(monkeypatch, 'GPU-alpha,GPU-beta', ['alpha', 'wrong-device'])
    with pytest.raises(RuntimeError, match='device 1'):
        cuda_runtime.prepare_cuda_device()


def test_visibility_cannot_change_after_cuda_initialization(monkeypatch):
    calls = setup_cuda(monkeypatch, 'GPU-alpha,GPU-beta', [], initialized=True)
    with pytest.raises(RuntimeError, match='before CUDA initialization'):
        cuda_runtime.prepare_cuda_device()
    assert not calls
