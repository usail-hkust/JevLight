"""Opt-in coalescing of complete simulation steps before native GPU batching.

Experimental CPU candidate only; the service rejects this mode until native
input and answer-validation failures can be attributed to each caller.
This schedules one combined native call; it does not establish GPU execution or
speedup. Those still require the runtime's chunk evidence and hardware tests.
No model thread, retry, partial-step return or timer progress is introduced.
"""
from collections import deque
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import threading
import time
import uuid


@dataclass
class _Step:
    requests: list
    capacity: int
    notify: object
    submitted: float = field(default_factory=time.monotonic)
    results: object = None
    error: object = None
    done: bool = False


class SharedBatchBackend:
    """FIFO callers elect one executor, retaining each step's native capacity.

    Adjacent steps with the same capacity may share a native call. Each step
    remains complete and each response is sliced back to its original caller.
    The original backend lock continues to serialize access to the model.
    """

    def __init__(self, backend, *, window_ms, max_steps=2):
        if isinstance(window_ms, bool) or not math.isfinite(window_ms) or window_ms <= 0:
            raise ValueError('shared batch window must be finite and positive')
        if type(max_steps) is not int or max_steps < 2:
            raise ValueError('shared batch max_steps must be an integer of at least two')
        self.backend = backend
        self.window = window_ms / 1000
        self.max_steps = max_steps
        self._condition = threading.Condition()
        self._pending = deque()
        self._running = False

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def evaluate_batch(self, requests, batch_size):
        maximum = int(self.backend.config.get('batch_size', 16))
        if type(batch_size) is not int or not 1 <= batch_size <= maximum:
            raise ValueError(f'batch_size must be between 1 and {maximum}')
        requests = list(requests)
        if not requests:
            return []
        progress = self.backend.runtime._step_progress
        step = _Step(requests, batch_size, getattr(progress, 'notify', None))
        condition = self._condition
        with condition:
            self._pending.append(step)
            condition.notify_all()
        while True:
            with condition:
                if step.done:
                    if step.error is not None:
                        raise step.error
                    return step.results
                if self._running or self._pending[0] is not step:
                    condition.wait()
                    continue
                self._running = True
                deadline = step.submitted + self.window
                # Wake on arrivals; never wait for an absent second simulator
                # beyond the explicit deployment scheduling window.
                while len(self._pending) < self.max_steps:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    condition.wait(remaining)
                group = []
                while (self._pending and len(group) < self.max_steps
                       and self._pending[0].capacity == step.capacity):
                    group.append(self._pending.popleft())
            try:
                self._execute(group, progress)
            finally:
                with condition:
                    self._running = False
                    condition.notify_all()

    def _execute(self, group, progress):
        previous = getattr(progress, 'notify', None)
        disconnected = set()

        def completed():
            for index, step in enumerate(group):
                if step.notify is not None and index not in disconnected:
                    try:
                        step.notify()
                    except OSError:
                        # A disconnected HTTP consumer must not abort another
                        # simulation's GPU work. Its final HTTP write still fails.
                        disconnected.add(index)

        progress.notify = completed
        started = time.monotonic()
        group_id = uuid.uuid4().hex
        requests = [request for step in group for request in step.requests]
        reports = []
        offset = 0
        for index, step in enumerate(group):
            reports.append(dict(group_id=group_id, steps=len(group), step_index=index,
                                request_offset=offset, step_requests=len(step.requests),
                                combined_requests=len(requests), capacity=step.capacity,
                                queue_wait_ms=(started-step.submitted)*1000))
            offset += len(step.requests)
        event = dict(group_id=group_id, combined_requests=len(requests),
                     capacity=group[0].capacity, steps=reports)
        try:
            results = self.backend.evaluate_batch(requests, group[0].capacity)
            if len(results) != len(requests):
                raise ValueError('shared native batch result count mismatch')
            offset = 0
            for step, report in zip(group, reports, strict=True):
                step.results = results[offset:offset + len(step.requests)]
                for result in step.results:
                    result.setdefault('usage', {})['shared_batch'] = report
                offset += len(step.requests)
            event['status'] = 'completed'
        except BaseException as error:
            # No scheduler retry or serial fallback: preserve the original
            # failure for every affected caller and release all waiters.
            for step in group:
                step.error = error
            event.update(status='failed', error=f'{type(error).__name__}: {error}')
        finally:
            progress.notify = previous
            event.update(wall_ms=(time.monotonic()-started)*1000, updated_at=time.time())
            self.last_shared_batch = event
            try:
                log = getattr(self.backend, 'log_path', None)
                if log:
                    log = Path(log)
                    with log.with_name(log.stem + '_shared_batch.jsonl').open('a') as stream:
                        stream.write(json.dumps(event, ensure_ascii=False) + '\n')
            except Exception as error:
                for step in group:
                    if step.error is None:
                        step.error = error
            with self._condition:
                for step in group:
                    step.done = True
                self._condition.notify_all()
