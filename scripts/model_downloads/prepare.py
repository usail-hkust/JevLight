"""Download, verify and encode selected models without starting GPU or traffic jobs."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.model_downloads.download import CATALOG, model_keys, now, save, snapshot
from scripts.experiments.preflight import cpu_preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', required=True)
    parser.add_argument('--author-environment', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--range-workers', type=int, default=2)
    parser.add_argument('--verify-existing', action='store_true', help='Skip downloading; require complete existing snapshots')
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text())
    keys = model_keys(args.models, catalog)
    if args.workers < 1 or args.range_workers < 1 or any(key not in catalog for key in keys):
        parser.error('Use known model keys and positive worker counts')
    environment = args.author_environment.resolve()
    if not (environment / 'uv.lock').is_file():
        parser.error('author-environment must contain a frozen uv.lock')
    os.environ.update(CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1', TOKENIZERS_PARALLELISM='false')
    failed = False
    for key in keys:
        directory = ROOT / 'results' / key / 'preparation'
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'prepare.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            record = dict(model=key, identity=catalog[key], started_at=now(),
                          status='preparing', stage='download', gpu_acceptance='not_run',
                          formal_experiments='not_started')
            # Preserve earlier evidence when retrying after an interruption.
            path = directory / ('prepare_' + now().replace(':', '-') + '.json')
            save(path, record)
            try:
                if not args.verify_existing:
                    snapshot(key, catalog[key]['model_id'], catalog[key]['revision'],
                             workers=args.workers, range_workers=args.range_workers)
                record['stage'] = 'integrity'
                save(path, record)
                subprocess.run([sys.executable, 'scripts/model_downloads/verify_snapshots.py',
                                '--models', key], cwd=ROOT, check=True)
                record['weights'] = 'verified'
                record['stage'] = 'cpu_encoding'
                save(path, record)
                record['cpu_report'] = str(cpu_preflight(ROOT, key, environment))
                record.update(status='cpu_prepared', stage='complete',
                              remaining=['engine validation', 'full-step GPU capacity and speed',
                                         'device and mode qualification', 'SUMO smoke'])
            except Exception as error:
                failed = True
                record.update(status='blocked', reason=f'{type(error).__name__}: {error}')
            record['finished_at'] = now()
            save(path, record)
            print(json.dumps(record), flush=True)
    raise SystemExit(int(failed))


if __name__ == '__main__':
    main()
