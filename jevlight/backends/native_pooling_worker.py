"""vLLM worker entrypoint that restores process-local native registrations."""
import json
import os
from pathlib import Path
import re
import time

from jevlight.backends.native_pooling_registry import register_native_pooling_models

# vLLM resolves this qualified worker class in each worker process before
# constructing it and loading weights. Do not rely on the parent's registry.
register_native_pooling_models()

from vllm.v1.worker.gpu_worker import Worker


class NativePoolingWorker(Worker):
    """Expose process-local completed forwards through the worker RPC API.

    Recording is explicitly armed per step, after engine startup/profiling.
    Each worker owns a separate append-only file, readable while encode is
    blocked in another process. These methods do not enable TP or change batch
    scheduling; the driver must still verify every expected worker's evidence.
    """

    def verify_lev_adapter(self, source):
        """Check the loaded unsharded adapter in the process owning its tensors."""
        if self.parallel_config.tensor_parallel_size != 1:
            raise ValueError('Sharded native adapter verification is not qualified')
        from jevlight.backends.lev_vllm_runtime import verify_adapter
        count = verify_adapter(self.model_runner.model, Path(source))
        return dict(rank=int(self.rank), tensor_count=count)

    def load_model(self, *, load_dummy_weights=False):
        if getattr(self, '_native_step', None) is not None:
            raise RuntimeError('Cannot reload a model during a recorded native step')
        super().load_model(load_dummy_weights=load_dummy_weights)
        self._native_step = None
        previous = getattr(self, '_native_forward_hook', None)
        if previous is not None:
            previous.remove()
        self._native_forward_hook = self.model_runner.model.register_forward_hook(
            self._native_completed_forward, with_kwargs=True)

    def begin_native_step(self, step_id, evidence_dir):
        """Arm a unique measurement; callable via LLM.collective_rpc."""
        import torch

        if getattr(self, '_native_step', None) is not None:
            raise RuntimeError('A native step is already being recorded')
        if not isinstance(step_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', step_id):
            raise ValueError('Native step identity must be a safe nonempty identifier')
        directory = Path(evidence_dir)
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError('Native evidence directory must be an existing absolute directory')
        # Linux process start identity distinguishes a reused PID in saved logs.
        start_ticks = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]
        identity = dict(step_id=step_id, rank=int(self.rank), pid=os.getpid(),
                        start_ticks=start_ticks, device=str(self.device),
                        gpu_uuid=str(torch.cuda.get_device_properties(self.device).uuid))
        torch.cuda.synchronize(self.device)
        free, total = torch.cuda.mem_get_info(self.device)
        identity.update(initial_free_bytes=int(free), memory_total_bytes=int(total),
                        initial_reserved_bytes=int(torch.cuda.memory_reserved(self.device)))
        path = directory / f'{step_id}.rank{self.rank}.pid{os.getpid()}.jsonl'
        # Exclusive creation preserves previous attempts, including empty ones.
        with path.open('x') as stream:
            stream.write(json.dumps(dict(identity, event='armed')) + '\n')
        # Reset in the owning process, after prior CUDA work has completed.
        # Driver allocator counters cannot measure a multiprocessing worker.
        torch.cuda.synchronize(self.device)
        torch.cuda.reset_peak_memory_stats(self.device)
        self._native_step = dict(identity=identity, path=path, forwards=[])
        return dict(identity, evidence_path=str(path))

    def _native_completed_forward(self, module, args, kwargs, value):
        step = getattr(self, '_native_step', None)
        if step is None:
            return  # Startup profiling/warmup is not request execution evidence.
        import torch
        from vllm.forward_context import get_forward_context

        metadata = get_forward_context().attn_metadata
        values = list(metadata.values()) if isinstance(metadata, dict) else [metadata]
        rows = max((int(item.query_start_loc.numel() - 1) for item in values
                    if getattr(item, 'query_start_loc', None) is not None), default=0)
        input_ids = kwargs.get('input_ids')
        if (rows < 1 or input_ids is None or not input_ids.is_cuda
                or str(input_ids.device) != str(self.device)):
            raise ValueError('Actual worker GPU sequence mapping is unavailable')
        # A completed Python call alone does not prove completed CUDA work.
        torch.cuda.synchronize(self.device)
        free, total = torch.cuda.mem_get_info(self.device)
        event = dict(step['identity'], event='forward_completed',
                     chunk=len(step['forwards']) + 1, rows=rows,
                     input_tokens=int(input_ids.numel()), completed_at_ns=time.time_ns(),
                     memory_allocated_bytes=int(torch.cuda.memory_allocated(self.device)),
                     memory_reserved_bytes=int(torch.cuda.memory_reserved(self.device)),
                     memory_peak_allocated_bytes=int(torch.cuda.max_memory_allocated(self.device)),
                     memory_peak_reserved_bytes=int(torch.cuda.max_memory_reserved(self.device)),
                     memory_free_bytes=int(free), memory_total_bytes=int(total))
        with step['path'].open('a') as stream:
            stream.write(json.dumps(event) + '\n')
        step['forwards'].append(event)

    def finish_native_step(self, step_id):
        """Return only this step's evidence; never count a prior/warmup forward."""
        step = getattr(self, '_native_step', None)
        if step is None or step['identity']['step_id'] != step_id:
            raise ValueError('Native step identity differs from the armed step')
        report = dict(step['identity'], evidence_path=str(step['path']),
                      forwards=list(step['forwards']))
        with step['path'].open('a') as stream:
            stream.write(json.dumps(dict(step['identity'], event='disarmed',
                                         completed_chunks=len(step['forwards']))) + '\n')
        self._native_step = None
        return report
