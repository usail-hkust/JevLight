"""Checkpoint corruption/append/atomic commit guards and lossless state types."""
from collections import Counter, defaultdict
import math
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from jevlight.simulation_checkpoint import (
    ENV_FIELDS, INTERSECTION_FIELDS, CONTROLLER_FIELDS,
    OutputLease, SimulationCheckpoint, decode, encode, save_checkpoint, sha256,
)


def test_state_codec_preserves_relation_keys_factories_and_rng():
    data = {('tls', 'NT'): defaultdict(Counter, {('dst', 'ST'): Counter({('src', 'NL'): 3})}),
            'sets': (frozenset({'x'}), {'v1', 'v2'}),
            'random': np.random.get_state()}
    result = decode(json.loads(json.dumps(encode(data))))
    assert result[('tls', 'NT')][('new', 'WT')][('src', 'NL')] == 0
    assert result[('tls', 'NT')][('dst', 'ST')][('src', 'NL')] == 3
    assert result['sets'] == data['sets']
    assert np.array_equal(result['random'][1], data['random'][1])


def test_nonfinite_features_preserved_without_nonstandard_json():
    state = {'empty_lane': float('nan'), 'values': np.array([1., np.inf, -np.inf, np.nan])}
    result = decode(json.loads(json.dumps(encode(state), allow_nan=False)))
    assert math.isnan(result['empty_lane'])
    assert np.array_equal(result['values'], state['values'], equal_nan=True)


@pytest.fixture
def checkpoint(tmp_path):
    def save_state(path):
        Path(path).write_text('<snapshot><rngState/></snapshot>')
    inter = SimpleNamespace(**dict.fromkeys(INTERSECTION_FIELDS, 0), inter_id='tls')
    env = SimpleNamespace(**dict.fromkeys(ENV_FIELDS, 0))
    env._simulation_running = True
    env.current_time = 31
    env.get_current_time = lambda: 31
    env.list_intersection = [inter]
    env.traci_conn = SimpleNamespace(simulation=SimpleNamespace(saveState=save_state),
                                    getVersion=lambda: (22, 'SUMO test'))
    controller = SimpleNamespace(**dict.fromkeys(CONTROLLER_FIELDS, 0), trajectory_relations=None)
    trace = tmp_path / 'trace.jsonl'
    trace.write_text('{"step":0}\n')
    root = tmp_path / 'checkpoints'
    kwargs = dict(env=env, controller=controller, identity={'config': 'unchanged'},
                  loop={'step': 2, 'total_reward': -3}, append_paths=[trace])
    save_checkpoint(root, **kwargs)
    return root, kwargs, trace


def test_identity_rejected_before_any_output_mutation(checkpoint):
    root, kwargs, trace = checkpoint
    before = trace.read_bytes()
    with pytest.raises(ValueError, match='identity'):
        SimulationCheckpoint(root, identity={'config': 'different'})
    assert trace.read_bytes() == before


@pytest.mark.parametrize('component', ['python', 'sumo', 'dependencies'])
def test_runtime_mismatch_preserves_uncommitted_tail(checkpoint, component):
    root, kwargs, trace = checkpoint
    kwargs['identity']['runtime'] = {'python': 'old', 'sumo': 'old', 'dependencies': 'old'}
    save_checkpoint(root, **kwargs)
    trace.write_bytes(trace.read_bytes() + b'uncommitted tail\n')
    before = trace.read_bytes()
    changed = dict(kwargs['identity'], runtime=dict(kwargs['identity']['runtime'], **{component: 'new'}))
    with OutputLease(trace.parent) as lease:
        with pytest.raises(ValueError, match='identity mismatch'):
            SimulationCheckpoint(root, identity=changed, output_lease=lease, archive_tails=True)
    assert trace.read_bytes() == before
    assert not (trace.parent / '.resume-archives').exists()


def test_runtime_probe_binds_actual_binary_and_preserves_loader_error(tmp_path, monkeypatch):
    from jevlight.simulation_checkpoint import runtime_identity
    binary = tmp_path / 'sumo'
    binary.write_text('#!/bin/sh\necho "SUMO test build"\n')
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path))
    identity = runtime_identity()
    assert identity['sumo']['binary'] == {str(binary.resolve()): sha256(binary)}
    assert identity['sumo']['version'] == 'SUMO test build'
    assert identity['dependencies']['traci']['version']
    binary.write_text('#!/bin/sh\necho "libXrender original loader failure" >&2\nexit 127\n')
    with pytest.raises(RuntimeError, match='libXrender original loader failure'):
        runtime_identity()
    binary.unlink()
    with pytest.raises(FileNotFoundError, match='not found in PATH'):
        runtime_identity()


def test_tail_and_same_size_corruption_rejected_and_preserved(checkpoint):
    root, kwargs, trace = checkpoint
    original = trace.read_bytes()
    for content in (original + b'{"step":1}\n', original.replace(b'0', b'9')):
        trace.write_bytes(content)
        with pytest.raises(ValueError, match='append boundary'):
            SimulationCheckpoint(root, identity=kwargs['identity'])
        assert trace.read_bytes() == content


def test_corrupt_state_rejected(checkpoint):
    root, kwargs, _ = checkpoint
    pointer = json.loads((root / 'latest.json').read_text())
    (root / pointer['generation'] / 'python.json').write_text('[]')
    with pytest.raises(ValueError, match='state hash'):
        SimulationCheckpoint(root, identity=kwargs['identity'])


def test_failed_generation_does_not_replace_last_commit(checkpoint):
    root, kwargs, _ = checkpoint
    before = (root / 'latest.json').read_bytes()
    kwargs['env'].traci_conn.simulation.saveState = lambda path: Path(path).write_text('<snapshot/>')
    with pytest.raises(ValueError, match='RNG'):
        save_checkpoint(root, **kwargs)
    assert (root / 'latest.json').read_bytes() == before
    assert len(list(root.glob('checkpoint-*'))) == 2
    assert SimulationCheckpoint(root, identity=kwargs['identity']).state['loop']['step'] == 2


def test_restore_checks_before_python_state_changes(checkpoint):
    root, kwargs, _ = checkpoint
    cp = SimulationCheckpoint(root, identity=kwargs['identity'])
    kwargs['env'].traci_conn.getVersion = lambda: (23, 'other')
    kwargs['env'].current_time = 99
    with pytest.raises(ValueError, match='version'):
        cp.restore_python(env=kwargs['env'], controller=kwargs['controller'])
    assert kwargs['env'].current_time == 99


def test_restore_recovers_loop_and_controller_at_same_time(checkpoint):
    root, kwargs, _ = checkpoint
    cp = SimulationCheckpoint(root, identity=kwargs['identity'])
    kwargs['controller'].previous_signals = {'unexpected': 'signal'}
    loop = cp.restore_python(env=kwargs['env'], controller=kwargs['controller'])
    assert loop == {'step': 2, 'total_reward': -3}
    assert kwargs['controller'].previous_signals == 0
    assert kwargs['env'].current_time == 31


def test_environment_configuration_mismatch_rejected(checkpoint):
    root, kwargs, _ = checkpoint
    cp = SimulationCheckpoint(root, identity=kwargs['identity'])
    kwargs['env'].dic_traffic_env_conf = {'MIN_ACTION_TIME': 30}
    kwargs['controller'].previous_signals = {'untouched': True}
    with pytest.raises(ValueError, match='Environment configuration'):
        cp.restore_python(env=kwargs['env'], controller=kwargs['controller'])
    assert kwargs['controller'].previous_signals == {'untouched': True}


def test_output_lease_excludes_other_process_and_releases(tmp_path):
    code = """
import sys
from jevlight.simulation_checkpoint import OutputLease
try:
    with OutputLease(sys.argv[1]):
        pass
except RuntimeError:
    sys.exit(23)
"""
    with OutputLease(tmp_path):
        assert subprocess.run([sys.executable, '-c', code, str(tmp_path)]).returncode == 23
    assert subprocess.run([sys.executable, '-c', code, str(tmp_path)]).returncode == 0
    assert (tmp_path / '.simulation-output.lock').exists()


def test_output_lease_released_after_abrupt_process_exit(tmp_path):
    code = """
import os, sys
from jevlight.simulation_checkpoint import OutputLease
lease = OutputLease(sys.argv[1]).__enter__()
os._exit(7)
"""
    assert subprocess.run([sys.executable, '-c', code, str(tmp_path)]).returncode == 7
    with OutputLease(tmp_path) as lease:
        lease.require([tmp_path / 'trace'])


def test_archive_tails_requires_lease_and_preserves_original_attempt(checkpoint):
    root, kwargs, trace = checkpoint
    prefix = trace.read_bytes()
    original = prefix + b'{"step":1}\n'
    trace.write_bytes(original)
    with pytest.raises(RuntimeError, match='ownership'):
        SimulationCheckpoint(root, identity=kwargs['identity'], archive_tails=True)
    assert trace.read_bytes() == original
    with OutputLease(trace.parent) as lease:
        cp = SimulationCheckpoint(root, identity=kwargs['identity'], output_lease=lease,
                                  archive_tails=True)
        assert trace.read_bytes() == prefix
        manifest = json.loads((cp.output_archive / 'manifest.json').read_text())
        record = manifest['outputs'][str(trace)]
        archived = cp.output_archive / record['archive_file']
        assert archived.read_bytes() == original
        assert sha256(archived) == record['sha256']
        assert (cp.output_archive / 'restored.json').exists()
        again = SimulationCheckpoint(root, identity=kwargs['identity'], output_lease=lease,
                                     archive_tails=True)
        assert again.output_archive is None
        assert len(list((trace.parent / '.resume-archives').iterdir())) == 1


def test_archive_prevalidates_all_prefixes_before_mutating_any(checkpoint):
    root, kwargs, trace = checkpoint
    other = trace.with_name('signals.txt')
    other.write_text('committed\n')
    kwargs['append_paths'].append(other)
    save_checkpoint(root, **kwargs)
    trace.write_bytes(trace.read_bytes() + b'valid tail\n')
    other.write_text('corrupted\n')
    before = {p: p.read_bytes() for p in (trace, other)}
    with OutputLease(trace.parent) as lease:
        with pytest.raises(ValueError, match='prefix mismatch'):
            SimulationCheckpoint(root, identity=kwargs['identity'], output_lease=lease,
                                 archive_tails=True)
    assert {p: p.read_bytes() for p in before} == before
    assert not (trace.parent / '.resume-archives').exists()


def test_archive_identity_mismatch_and_outside_lease_leave_outputs_untouched(checkpoint):
    root, kwargs, trace = checkpoint
    original = trace.read_bytes() + b'tail\n'
    trace.write_bytes(original)
    with OutputLease(root) as lease:
        with pytest.raises(ValueError, match='identity'):
            SimulationCheckpoint(root, identity={'wrong': True}, output_lease=lease,
                                 archive_tails=True)
        with pytest.raises(ValueError, match='outside'):
            SimulationCheckpoint(root, identity=kwargs['identity'], output_lease=lease,
                                 archive_tails=True)
    assert trace.read_bytes() == original


def test_partial_prefix_installation_can_resume_without_losing_originals(checkpoint, monkeypatch):
    root, kwargs, trace = checkpoint
    other = trace.with_name('signals.txt')
    other.write_text('committed\n')
    kwargs['append_paths'].append(other)
    save_checkpoint(root, **kwargs)
    prefixes = {p: p.read_bytes() for p in (trace, other)}
    originals = {p: b + b'uncommitted tail\n' for p, b in prefixes.items()}
    for path, content in originals.items():
        path.write_bytes(content)
    replace = os.replace
    def fail_second(src, dst):
        if Path(dst) == other:
            raise OSError('injected interrupted prefix installation')
        replace(src, dst)
    with OutputLease(trace.parent) as lease:
        with monkeypatch.context() as patch:
            patch.setattr(os, 'replace', fail_second)
            with pytest.raises(OSError, match='interrupted'):
                SimulationCheckpoint(root, identity=kwargs['identity'], output_lease=lease,
                                     archive_tails=True)
        assert trace.read_bytes() == prefixes[trace]
        assert other.read_bytes() == originals[other]
        first_archive = next((trace.parent / '.resume-archives').iterdir())
        saved = json.loads((first_archive / 'manifest.json').read_text())
        for path, original in originals.items():
            assert (first_archive / saved['outputs'][str(path)]['archive_file']).read_bytes() == original
        assert not (first_archive / 'restored.json').exists()
        SimulationCheckpoint(root, identity=kwargs['identity'], output_lease=lease,
                             archive_tails=True)
    assert {p: p.read_bytes() for p in prefixes} == prefixes
