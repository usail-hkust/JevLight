"""Serve a configured native decision model with complete-step batch progress."""
import argparse
import copy
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def load_selection(path):
    if path is None:
        return None
    selection = json.loads(Path(path).read_text())
    progress = (ROOT / selection['progress_path']).resolve()
    if not progress.is_relative_to(ROOT / 'results'):
        raise ValueError('Engine progress log must be inside results/')
    if int(selection['capacity']) <= 0:
        raise ValueError('Engine capacity must be positive')
    if set(selection['native_modes']) != {'jevlight', 'cojevlight'}:
        raise ValueError('Engine selection must describe both ordinary and cooperative inputs')
    progress.parent.mkdir(parents=True, exist_ok=True)
    return dict(selection, progress_path=str(progress),
                checkpoint=str((ROOT / selection['checkpoint']).resolve()))


def build_backend(config, *, batch_runtime='step', attention='native', selection=None):
    from jevlight.step_batch_support import validate_shared_batch_config
    validate_shared_batch_config(config)
    if selection is not None:
        if batch_runtime != 'step' or attention != 'native':
            raise ValueError('Engine selection cannot be combined with native kernel overrides')
        from jevlight.backends.transfer_vllm_runtime import backend
        return backend(config, selection)
    if batch_runtime == 'native' and config.get('inference_engine', 'author') != 'author':
        raise ValueError('Native batch installation requires the author inference engine')
    if batch_runtime == 'step' and attention != 'native':
        raise ValueError('Attention overrides require the native batch runtime')
    from jevlight.backends.decision_model_service import NativeBackend
    if batch_runtime == 'native':
        from jevlight.backends.native_batch_runtime import configure_execution, install
        configure_execution()
    result = NativeBackend(config)
    if batch_runtime == 'native':
        install(result, attention=attention)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--request-log', type=Path, required=True)
    parser.add_argument('--batch-runtime', choices=('step', 'native'), default='step')
    parser.add_argument('--attention', choices=('native', 'laya_sdpa', 'deberta_tiled'), default='native')
    parser.add_argument('--engine-selection', type=Path)
    parser.add_argument('--checkpoint-identity', action='store_true',
                        help='Capture native service identity evidence; does not qualify resume')
    args = parser.parse_args()
    config = tomllib.loads(args.config.read_text())
    log = args.request_log.resolve()
    if not log.is_relative_to(ROOT / 'results'):
        parser.error('request log must be inside results/')
    selection = load_selection(args.engine_selection)
    if args.checkpoint_identity and selection is not None:
        parser.error('Checkpoint identity for an external engine selection is not qualified')
    identity = None
    if args.checkpoint_identity:
        from jevlight.service_identity import capture_identity, service_document
        identity_config = copy.deepcopy(config)
        execution = dict(batch_runtime=args.batch_runtime, attention=args.attention)
        identity = capture_identity(ROOT, identity_config, execution=execution)
    log.parent.mkdir(parents=True, exist_ok=True)
    backend = build_backend(config, batch_runtime=args.batch_runtime,
                            attention=args.attention, selection=selection)
    if identity is not None:
        if capture_identity(ROOT, identity_config, execution=execution) != identity:
            raise ValueError('Native service identity changed during model loading')
        backend.service_identity = service_document(identity, backend)
    backend.log_path = log
    backend.step_progress_path = log.with_name(log.stem + '_batch_progress.json')
    from jevlight.step_batch_support import make_step_server
    server = make_step_server(backend, config.get('host', '127.0.0.1'),
                              config.get('port', 8123), config['model_id'])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
