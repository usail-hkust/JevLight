"""Read completed worker forwards without mistaking polling for progress."""
import json
from pathlib import Path
import threading


IDENTITY = ('step_id', 'rank', 'pid', 'start_ticks', 'device', 'gpu_uuid')
BASELINE = ('initial_free_bytes', 'initial_reserved_bytes', 'memory_total_bytes')


def gpu_uuid(value):
    return str(value).removeprefix('GPU-')


class WorkerEvidence:
    """Require every expected rank before reporting a completed TP chunk."""

    def __init__(self, armed, expected_uuids, step_id, directory, notify=None):
        self.workers = {}
        self.notify = notify
        self.completed = []
        self._stop = threading.Event()
        self._error = None
        if not expected_uuids or len(set(map(gpu_uuid, expected_uuids))) != len(expected_uuids):
            raise ValueError('Expected worker GPU UUIDs must be distinct')
        if len(armed) != len(expected_uuids):
            raise ValueError('Missing native worker registration')
        for report in armed:
            rank = report['rank']
            if type(rank) is not int or rank not in range(len(expected_uuids)) or rank in self.workers:
                raise ValueError('Unexpected or duplicate native worker rank')
            if report['step_id'] != step_id or gpu_uuid(report['gpu_uuid']) != gpu_uuid(expected_uuids[rank]):
                raise ValueError('Native worker step/GPU identity differs')
            stat = Path(f"/proc/{report['pid']}/stat").read_text()
            if stat.rsplit(')', 1)[1].split()[19] != report['start_ticks']:
                raise ValueError('Native worker process start identity differs')
            path = Path(report['evidence_path']).resolve()
            if path.parent != Path(directory).resolve() or not path.is_file():
                raise ValueError('Native worker evidence path differs')
            total = report.get('memory_total_bytes')
            if type(total) is not int or total < 1 or any(
                    type(report.get(key)) is not int or not 0 <= report[key] <= total
                    for key in BASELINE[:-1]):
                raise ValueError('Native worker baseline memory measurement is invalid')
            self.workers[rank] = dict(baseline={key: report[key] for key in BASELINE}, identity={key: report[key] for key in IDENTITY},
                                      path=path, offset=0, armed=False, disarmed=False, forwards=[])
        self.poll()

    def poll(self):
        for worker in self.workers.values():
            with worker['path'].open('rb') as stream:
                stream.seek(worker['offset'])
                while True:
                    line = stream.readline()
                    if not line.endswith(b'\n'):
                        break  # An in-flight append is not yet evidence.
                    event = json.loads(line)
                    if any(event.get(key) != value for key, value in worker['identity'].items()):
                        raise ValueError('Native forward identity differs')
                    if worker['disarmed']:
                        raise ValueError('Native evidence appended after disarm')
                    if any(event.get(key) != value for key, value in worker['baseline'].items()):
                        raise ValueError('Native worker baseline memory identity differs')
                    kind = event.get('event')
                    if kind == 'armed' and not worker['armed']:
                        worker['armed'] = True
                    elif kind == 'forward_completed' and worker['armed']:
                        if event.get('chunk') != len(worker['forwards']) + 1:
                            raise ValueError('Native forward chunk sequence differs')
                        for key in ('rows', 'input_tokens', 'completed_at_ns', 'memory_total_bytes'):
                            if type(event.get(key)) is not int or event[key] < 1:
                                raise ValueError('Native forward measurement is unavailable')
                        for key in ('memory_allocated_bytes', 'memory_reserved_bytes', 'memory_free_bytes',
                                    'memory_peak_allocated_bytes', 'memory_peak_reserved_bytes'):
                            if type(event.get(key)) is not int or not 0 <= event[key] <= event['memory_total_bytes']:
                                raise ValueError('Native worker memory measurement is invalid')
                        if event['memory_allocated_bytes'] > event['memory_reserved_bytes']:
                            raise ValueError('Native worker memory measurement is invalid')
                        if (event['memory_peak_allocated_bytes'] < event['memory_allocated_bytes']
                                or event['memory_peak_reserved_bytes'] < event['memory_reserved_bytes']
                                or event['memory_peak_allocated_bytes'] > event['memory_peak_reserved_bytes']):
                            raise ValueError('Native worker peak memory measurement is invalid')
                        previous = worker['forwards']
                        if previous and any(event[key] < previous[-1][key] for key in (
                                'memory_peak_allocated_bytes', 'memory_peak_reserved_bytes')):
                            raise ValueError('Native worker step peak memory decreased')
                        worker['forwards'].append(event)
                    elif kind == 'disarmed' and worker['armed']:
                        if event.get('completed_chunks') != len(worker['forwards']):
                            raise ValueError('Native worker disarm count differs')
                        worker['disarmed'] = True
                    else:
                        raise ValueError('Unexpected native worker evidence event')
                    worker['offset'] = stream.tell()
        count = min(len(worker['forwards']) for worker in self.workers.values())
        while len(self.completed) < count:
            index = len(self.completed)
            events = [self.workers[rank]['forwards'][index] for rank in sorted(self.workers)]
            if len({(event['rows'], event['input_tokens']) for event in events}) != 1:
                raise ValueError('Native TP worker sequence mapping differs')
            self.completed.append(events)
            if self.notify:
                self.notify()

    def start(self):
        def listen():
            try:
                while not self._stop.wait(.05):
                    self.poll()
            except BaseException as error:
                self._error = error
        self._thread = threading.Thread(target=listen, name='native-worker-evidence', daemon=True)
        self._thread.start()

    def memory_summary(self):
        """Per-rank measurements, including incomplete attempts.

        Peak headroom uses the pre-step free memory minus allocator growth,
        further limited by post-forward samples adjusted for allocator peaks.
        This is a conservative allocator estimate, not continuous device sampling.
        """
        reports = []
        for rank in sorted(self.workers):
            worker = self.workers[rank]
            events = worker['forwards']
            baseline = worker['baseline']
            peak_reserved = max((e['memory_peak_reserved_bytes'] for e in events), default=None)
            lower = None if peak_reserved is None else min(
                [baseline['initial_free_bytes'] - max(0, peak_reserved - baseline['initial_reserved_bytes'])]
                + [e['memory_free_bytes'] - max(0, peak_reserved - e['memory_reserved_bytes']) for e in events])
            reports.append(dict(worker['identity'], completed_chunks=len(events),
                peak_free_lower_bound_bytes=lower,
                initial_free_bytes=baseline['initial_free_bytes'],
                initial_reserved_bytes=baseline['initial_reserved_bytes'],
                peak_allocated_bytes=max((e['memory_peak_allocated_bytes'] for e in events), default=None),
                peak_reserved_bytes=max((e['memory_peak_reserved_bytes'] for e in events), default=None),
                min_observed_free_bytes=min((e['memory_free_bytes'] for e in events), default=None),
                memory_total_bytes=events[-1]['memory_total_bytes'] if events else None))
        return reports

    def stop(self):
        self._stop.set()
        self._thread.join()
        if self._error is not None:
            raise self._error
        self.poll()

    def finish(self, reports):
        self.poll()
        if len(reports) != len(self.workers) or {r['rank'] for r in reports} != set(self.workers):
            raise ValueError('Missing native worker finish report')
        for report in reports:
            worker = self.workers[report['rank']]
            if (any(report.get(key) != value for key, value in worker['identity'].items())
                    or any(report.get(key) != value for key, value in worker['baseline'].items())
                    or Path(report['evidence_path']).resolve() != worker['path']
                    or report['forwards'] != worker['forwards'] or not worker['disarmed']
                    or worker['offset'] != worker['path'].stat().st_size):
                raise ValueError('Native worker finish evidence differs')
        if not self.completed or any(len(w['forwards']) != len(self.completed) for w in self.workers.values()):
            raise ValueError('No complete native GPU execution on every worker')
