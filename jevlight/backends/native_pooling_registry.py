"""Importable native pooling registrations for driver and spawned workers.

The registry is process local. Registering in the service alone does not make
custom architectures available to a fresh vLLM worker.
"""
from transformers import AutoConfig
from vllm import ModelRegistry
from vllm.transformers_utils.configs.qwen3_5 import Qwen3_5Config, Qwen3_5TextConfig


class ValenConfig(Qwen3_5Config):
    model_type = 'valen_qwen'


class ValenDecision15Config(Qwen3_5Config):
    # The 1.5 release keeps the published model_type; the generation is a
    # config field checked by the Valen-Decision-1.5 engine and runtime.
    model_type = 'valen_qwen'


NATIVE_POOLING_ARCHITECTURES = ('NativeMarkerEngine', 'ValenMarkerEngine')
NATIVE_POOLING_WORKER = 'jevlight.backends.native_pooling_worker.NativePoolingWorker'
VALEN_DECISION15_ARCHITECTURES = ('ValenDecision15MarkerEngine',)
VALEN_DECISION15_WORKER = 'jevlight.backends.valen_decision15_pooling_worker.ValenDecision15PoolingWorker'


def register_native_pooling_models():
    """Register lazily, without importing model implementations or using CUDA."""
    AutoConfig.register('qwen3_5_text', Qwen3_5TextConfig, exist_ok=True)
    AutoConfig.register('valen_qwen', ValenConfig, exist_ok=True)
    for architecture in NATIVE_POOLING_ARCHITECTURES:
        ModelRegistry.register_model(
            architecture, f'jevlight.backends.marker_vllm_models:{architecture}')


def register_valen_decision15_pooling_models():
    """Process-local Valen-Decision-1.5 registration.

    Both generations publish ``model_type = valen_qwen``. A service process
    hosts one checkpoint, so the 1.5 runtime and its worker replace the config
    class for that type here; a Valen 1.0 process never calls this function.
    """
    register_native_pooling_models()
    AutoConfig.register('valen_qwen', ValenDecision15Config, exist_ok=True)
    for architecture in VALEN_DECISION15_ARCHITECTURES:
        ModelRegistry.register_model(
            architecture, f'jevlight.backends.marker_vllm_models:{architecture}')
