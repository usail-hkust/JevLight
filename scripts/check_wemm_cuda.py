"""Exercise the author's CUDA convolution and check the Transformers binding."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import time


def check():
    import torch
    from torch.nn import functional as F
    from transformers.models.qwen3_5 import modeling_qwen3_5

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    qwen_kernel = getattr(modeling_qwen3_5, "causal_conv1d_fn", None)
    if not callable(qwen_kernel):
        raise RuntimeError("Transformers Qwen3.5 causal convolution is unavailable")
    generator = torch.Generator(device="cuda").manual_seed(731)
    with torch.inference_mode():
        x = torch.randn((1, 5120, 4096), generator=generator, device="cuda", dtype=torch.bfloat16)
        weight = torch.randn((5120, 4), generator=generator, device="cuda", dtype=x.dtype)

        def reference():
            return F.silu(F.conv1d(x, weight[:, None], padding=3, groups=x.shape[1])[..., :x.shape[-1]])

        def accelerated():
            return qwen_kernel(x, weight, activation="silu")

        actual, expected = accelerated(), reference()
        torch.testing.assert_close(actual, expected, atol=0.0625, rtol=0.05)
        if not torch.isfinite(actual).all().item():
            raise RuntimeError("CUDA convolution returned nonfinite values")
        measurements = {}
        for name, function in (("reference_ms", reference), ("cuda_ms", accelerated)):
            for _ in range(3):
                function()
            torch.cuda.synchronize()
            started = time.perf_counter()
            for _ in range(10):
                function()
            torch.cuda.synchronize()
            measurements[name] = (time.perf_counter() - started) * 1000 / 10
    return dict(status="ready", checked_at=datetime.now(timezone.utc).isoformat(),
                torch=torch.__version__, cuda=torch.version.cuda,
                gpu=torch.cuda.get_device_name(),
                causal_conv1d=importlib.metadata.version("causal-conv1d"),
                max_absolute_error=(actual.float() - expected.float()).abs().max().item(),
                shape=list(x.shape), **measurements,
                note="Kernel microbenchmark only; does not predict full-model speed or identical decisions.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = check()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
