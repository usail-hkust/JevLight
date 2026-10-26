"""CUDA deployment checks shared by native decision engine adapters."""
import os
import subprocess


def prepare_cuda_device(*, required_version='12.8'):
    """Retain the engine ABI constraint and accept standard CUDA device selection.

    UUID lists are resolved before initialization for engines which require
    numeric visibility. Every UUID is checked in its requested logical order.
    Numeric indices and unset visibility retain CUDA's normal selection rules.
    """
    import torch

    if torch.version.cuda != required_version:
        raise RuntimeError(f'This engine requires the validated CUDA {required_version} runtime')
    if 'cuda-compat' in os.environ.get('LD_LIBRARY_PATH', ''):
        raise RuntimeError('This engine has not been validated with CUDA compatibility libraries')
    visible = os.environ.get('CUDA_VISIBLE_DEVICES')
    if visible is not None and (not visible.strip() or visible.strip() == '-1'):
        raise ValueError('The decision engine requires a visible CUDA device')
    selected = [item.strip() for item in visible.split(',')] if visible else []
    if any(item.startswith('GPU-') for item in selected):
        if not all(item.startswith('GPU-') for item in selected):
            raise ValueError('Select CUDA devices with either UUIDs or indices, not a mixture')
        if len(set(selected)) != len(selected):
            raise ValueError('CUDA device UUIDs must be distinct')
        if torch.cuda.is_initialized():
            raise RuntimeError('Resolve UUID visibility before CUDA initialization')
        inventory = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=index,uuid', '--format=csv,noheader'], text=True
        )
        indices = {uuid.strip(): index.strip() for index, uuid in
                   (line.split(',', 1) for line in inventory.splitlines())}
        if any(uuid not in indices for uuid in selected):
            raise ValueError('The selected GPU UUID is not present')
        os.environ['CUDA_VISIBLE_DEVICES'] = ','.join(indices[uuid] for uuid in selected)
        for logical_index, requested in enumerate(selected):
            actual = 'GPU-' + str(torch.cuda.get_device_properties(logical_index).uuid).removeprefix('GPU-')
            if actual != requested:
                raise RuntimeError(f'CUDA device {logical_index} differs from the requested UUID')


def configure_cpu_threads(default=4):
    """Respect explicit deployment thread limits; keep the existing default."""
    import torch

    threads = int(os.environ.get('OMP_NUM_THREADS', str(default)))
    if threads < 1:
        raise ValueError('OMP_NUM_THREADS must be positive')
    os.environ.setdefault('OMP_NUM_THREADS', str(threads))
    os.environ.setdefault('MKL_NUM_THREADS', str(threads))
    torch.set_num_threads(threads)
