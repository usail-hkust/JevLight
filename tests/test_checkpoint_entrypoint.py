"""Entry-point guards prevent unqualified services or output mutation on failure."""
import pytest

import run_jevlight as runner
from jevlight.env_bridge import JevLightEnv


@pytest.mark.parametrize('extra,message', [
    ([], 'local complete-step batch transport'),
    (['--mock_jev', '--use_wandb'], 'logger resume identity'),
])
def test_unqualified_checkpoint_rejected_before_sumo_or_output(monkeypatch, extra, message):
    monkeypatch.setattr(runner, 'JevLightEnv', lambda *a, **kw: pytest.fail('SUMO started'))
    monkeypatch.setattr(runner, 'build_configs', lambda *a: pytest.fail('Outputs planned'))
    args = runner.parse_args(['--jev_transport', 'local', '--checkpoint_every_steps', '2', *extra])
    with pytest.raises(ValueError, match=message):
        runner.run(args)


@pytest.mark.parametrize('flags', [
    ['--checkpoint_every_steps', '-1'], ['--archive_resume_tails'],
])
def test_invalid_checkpoint_operations_rejected(flags):
    with pytest.raises(SystemExit):
        runner.parse_args(flags)


@pytest.mark.parametrize('error', [FileNotFoundError('sumo missing'),
                                  RuntimeError('libXrender loader error')])
def test_runtime_failure_precedes_output_planning_or_sumo(monkeypatch, error):
    import jevlight.simulation_checkpoint as core
    def fail():
        raise error
    monkeypatch.setattr(core, 'runtime_identity', fail)
    monkeypatch.setattr(runner, 'JevLightEnv', lambda *a, **kw: pytest.fail('SUMO started'))
    monkeypatch.setattr(runner, 'build_configs', lambda *a: pytest.fail('Outputs planned'))
    args = runner.parse_args(['--mock_jev', '--jev_transport', 'local',
                             '--checkpoint_every_steps', '2'])
    with pytest.raises(type(error), match=str(error)):
        runner.run(args)


def test_live_identity_probe_failure_precedes_output_planning(monkeypatch):
    from jevlight import service_identity
    def fail(*args, **kwargs):
        raise ValueError('original service identity failure')
    monkeypatch.setattr(service_identity, 'probe_service_identity', fail)
    monkeypatch.setattr(runner, 'build_configs', lambda *a: pytest.fail('Outputs planned'))
    monkeypatch.setattr(runner, 'JevLightEnv', lambda *a, **kw: pytest.fail('SUMO started'))
    args = runner.parse_args(['--jev_transport', 'local', '--jev_batch_size', '196',
                             '--checkpoint_every_steps', '2'])
    with pytest.raises(ValueError, match='original service identity failure'):
        runner.run(args)


@pytest.mark.parametrize('fail_reset', [False, True])
def test_bridge_loads_directly_without_starting_fresh_simulation(tmp_path, monkeypatch, fail_reset):
    import jevlight.env_bridge as bridge
    calls = []
    class Environment:
        def __init__(self, **kwargs):
            self.closed = False
            calls.append(self)
        def reset(self, **kwargs):
            calls.append((self._start_time, kwargs))
            if fail_reset:
                raise RuntimeError('original SUMO startup error')
        def close(self):
            self.closed = True
    monkeypatch.setattr(bridge, 'SUMOEnv', Environment)
    paths = {key: str(tmp_path / suffix) for key, suffix in [
        ('PATH_TO_WORK_DIRECTORY', 'run'), ('PATH_TO_MODEL', 'model'), ('PATH_TO_ERROR', 'error')]}
    def start():
        return JevLightEnv({}, {}, paths, 'traffic.json', load_state_path='sumo.xml', start_time=30)
    if fail_reset:
        with pytest.raises(RuntimeError, match='original SUMO startup error'):
            start()
        assert calls[0].closed
    else:
        assert start().env is calls[0]
        assert not calls[0].closed
    assert calls[1] == (30, {'load_state_path': 'sumo.xml'})
