from types import SimpleNamespace
import pytest

from jevlight import sumo_runtime as runtime


def test_python_environment_precedes_system_path(tmp_path, monkeypatch):
    python = tmp_path/'Scripts/python.exe'
    python.parent.mkdir()
    python.touch()
    bundled = python.with_name('sumo.exe')
    bundled.touch()
    monkeypatch.delenv('SUMO_BINARY', raising=False)
    monkeypatch.setattr(runtime.sys, 'executable', str(python))
    monkeypatch.setattr(runtime.shutil, 'which', lambda _: 'system-sumo-1.24')
    assert runtime.resolve_sumo_binary() == str(bundled)


@pytest.mark.parametrize('version', ['1.24.0', '1.28.0', '1.28.1'])
def test_runtime_accepts_only_the_matched_release(monkeypatch, version):
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=f'Eclipse SUMO sumo Version {version}', stderr=''))
    if version == '1.28.0':
        assert runtime.require_sumo_128('chosen-sumo') == 'chosen-sumo'
    else:
        with pytest.raises(RuntimeError, match='1.28.0 is required'):
            runtime.require_sumo_128('chosen-sumo')
