"""Importable native pooling registrations for driver and spawned workers.

The registry is process local. Registering in the service alone does not make
custom architectures available to a fresh vLLM worker.
"""
from transformers import AutoConfig
from vllm import ModelRegistry
from vllm.transformers_utils.configs.qwen3_5 import Qwen3_5Config, Qwen3_5TextConfig


class ValenConfig(Qwen3_5Config):
    model_type = 'valen_qwen'


NATIVE_POOLING_ARCHITECTURES = ('NativeMarkerEngine', 'ValenMarkerEngine')
NATIVE_POOLING_WORKER = 'jevlight.backends.native_pooling_worker.NativePoolingWorker'


def register_native_pooling_models():
    """Register lazily, without importing model implementations or using CUDA."""
    AutoConfig.register('qwen3_5_text', Qwen3_5TextConfig, exist_ok=True)
    AutoConfig.register('valen_qwen', ValenConfig, exist_ok=True)
    for architecture in NATIVE_POOLING_ARCHITECTURES:
        ModelRegistry.register_model(
            architecture, f'jevlight.backends.marker_vllm_models:{architecture}')
