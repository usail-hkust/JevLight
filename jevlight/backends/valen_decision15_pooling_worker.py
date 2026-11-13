"""vLLM worker entrypoint for Valen-Decision-1.5; restores its process-local registrations."""
from jevlight.backends.native_pooling_registry import register_valen_decision15_pooling_models
from jevlight.backends.native_pooling_worker import NativePoolingWorker

# Importing the shared worker registers the Valen 1.0 config for the common
# ``valen_qwen`` model type. A 1.5 worker replaces it before loading weights.
register_valen_decision15_pooling_models()


class ValenDecision15PoolingWorker(NativePoolingWorker):
    """Same step evidence as the shared worker, plus the engine's block-mask row counts."""

    def valen_decision15_block_rows(self):
        """Rows forwarded under the block mask and with the causal kernel since the last call."""
        model = self.model_runner.model
        report = dict(rank=int(self.rank), block_rows=model.block_rows, causal_rows=model.causal_rows)
        model.block_rows = model.causal_rows = 0
        return report
