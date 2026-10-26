"""StartLux-Decision native runtime: vLLM 0.19.1 + the official StartLux server.

The official vLLM plugin is required for Instant (prompt-bidirectional) folders.
Each worker owns one vLLM process and one StartLux ``/v1/systemone`` process on
ports derived from the step-server port, so a queue can pin one model to one
GPU without a shared proxy.
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def gpu_index(value) -> str:
    """Accept a CUDA index or a GPU UUID and return the index vLLM can parse."""
    value = str(value)
    if not value.startswith("GPU-"):
        return value
    output = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"], text=True)
    for line in output.splitlines():
        index, uuid = [part.strip() for part in line.split(",", 1)]
        if uuid == value:
            return index
    raise ValueError(f"CUDA device {value} is not present on this host")


def _scalar(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _text_lines(value, indent: int = 0) -> list[str]:
    pad = " " * indent
    lines = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}{key}:")
                lines.extend(_text_lines(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {_scalar(item)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}-")
                lines.extend(_text_lines(item, indent + 2))
            else:
                lines.append(f"{pad}- {_scalar(item)}")
    else:
        lines.append(f"{pad}{_scalar(value)}")
    return lines


def state_as_text(state) -> str:
    """Render a JSON state as indented key/value evidence for models weak at nested JSON."""
    if isinstance(state, str):
        return state
    if state is None:
        return ""
    return "\n".join(_text_lines(state))


class StartLuxNative:
    """Proxy one StartLux model, starting its two servers when no URL is given."""

    def __init__(self, config):
        self.config = config
        self.model_id = config["model_id"]
        self.weights = (ROOT / config["weights_path"]).resolve()
        self.max_model_len = int(config.get("max_length", 65536))
        self.max_batched_tokens = int(config.get("max_num_batched_tokens", self.max_model_len))
        self.tensor_parallel = max(1, int(config.get("tensor_parallel_size", 1)))
        self.gpu = gpu_index(config.get("gpu", os.environ.get("CUDA_VISIBLE_DEVICES", "0")))
        self.step_port = int(config.get("port", 8123))
        self.vllm_port = int(config.get("vllm_port", self.step_port + 1000))
        self.server_port = int(config.get("server_port", self.step_port + 2000))
        self.overlay = Path(os.environ.get(
            "STARTLUX_OVERLAY", config.get("overlay_path",
                                           ".local/environments/startlux-vllm/overlay")))
        if not self.overlay.is_absolute():
            self.overlay = ROOT / self.overlay
        self.concurrency = int(config.get("http_concurrency", 32))
        self.state_format = config.get("state_format", "json")
        self.timeout = float(config.get("request_timeout", 3600))
        self.startup_timeout = float(config.get("startup_timeout", 1800))
        self.gpu_memory_utilization = float(config.get("gpu_memory_utilization", 0.85))
        self.processes = []
        self.log_paths = []
        base_url = config.get("base_url")
        if base_url:
            self.server_url = str(base_url).rstrip("/")
        else:
            self.server_url = f"http://127.0.0.1:{self.server_port}"
            self._launch()
        atexit.register(self.close)

    # ------------------------------------------------------------------ servers
    def _environment(self) -> dict:
        environment = os.environ.copy()
        previous = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = str(self.overlay) + (os.pathsep + previous if previous else "")
        environment.update(
            CUDA_VISIBLE_DEVICES=self.gpu,
            STARTLUX_PREFIX_BIDIR="1",
            VLLM_NO_USAGE_STATS="1",
            VLLM_PLUGINS="startlux_prefix_bidir",
            TOKENIZERS_PARALLELISM="false",
        )
        return environment

    def _log(self, suffix: str) -> Path:
        directory = ROOT / "results/experiments/logs"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"startlux_{self.model_id.split('/')[-1]}_gpu{self.gpu}_{suffix}.log"
        self.log_paths.append(path)
        return path

    def _launch(self) -> None:
        environment = self._environment()
        vllm_log = self._log("vllm").open("a")
        vllm_command = [
            sys.executable, "-m", "vllm.entrypoints.openai.api_server",
            "--model", str(self.weights),
            "--served-model-name", self.model_id,
            "--host", "127.0.0.1", "--port", str(self.vllm_port),
            "--max-model-len", str(self.max_model_len),
            "--tensor-parallel-size", str(self.tensor_parallel),
            "--gpu-memory-utilization", str(self.gpu_memory_utilization),
            "--logprobs-mode", "processed_logprobs", "--max-logprobs", "26",
            "--generation-config", "vllm",
            "--no-enable-prefix-caching", "--no-enable-chunked-prefill",
            "--max-num-batched-tokens", str(self.max_batched_tokens),
            "--limit-mm-per-prompt", json.dumps({"image": 0, "video": 0}, separators=(",", ":")),
            "--disable-uvicorn-access-log",
        ]
        self.processes.append((subprocess.Popen(
            vllm_command, cwd=ROOT, env=environment, stdout=vllm_log,
            stderr=subprocess.STDOUT, start_new_session=True), vllm_log.name))
        self._wait(f"http://127.0.0.1:{self.vllm_port}/health", "vLLM")

        serve_log = self._log("serve").open("a")
        serve_command = [
            sys.executable, "-m", "startlux_decide.cli", "serve",
            "--model", str(self.weights),
            "--backend", "vllm",
            "--vllm-url", f"127.0.0.1:{self.vllm_port}",
            "--host", "127.0.0.1", "--port", str(self.server_port),
            "--no-images", "--max-model-len", str(self.max_model_len),
        ]
        self.processes.append((subprocess.Popen(
            serve_command, cwd=ROOT, env=environment, stdout=serve_log,
            stderr=subprocess.STDOUT, start_new_session=True), serve_log.name))
        self._wait(f"{self.server_url}/health", "StartLux")

    @staticmethod
    def _tail(path: str, lines: int = 40) -> str:
        try:
            content = Path(path).read_text(errors="replace").splitlines()
        except OSError:
            return ""
        return "\n".join(content[-lines:])

    def _wait(self, url: str, name: str) -> None:
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            for process, log_name in self.processes:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"{name} exited with {process.returncode} before becoming healthy; "
                        f"log {log_name}:\n{self._tail(str(ROOT / 'results/experiments/logs' / log_name))}")
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                pass
            time.sleep(2)
        raise TimeoutError(f"{name} did not become healthy at {url} within {self.startup_timeout}s")

    def close(self) -> None:
        for process, _ in reversed(self.processes):
            if process.poll() is not None:
                continue
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                continue
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        self.processes.clear()

    # ------------------------------------------------------------------- native
    def encode(self, request):
        return {
            "state_characters": len(json.dumps(request.get("state"), ensure_ascii=False)),
            "questions": len(request.get("questions", {})),
        }

    def _prepare(self, request):
        if self.state_format != "text":
            return request
        return dict(request, state=state_as_text(request.get("state")))

    def _post(self, request):
        request = self._prepare(request)
        body = json.dumps(request, ensure_ascii=False).encode()
        last = None
        for attempt in range(3):
            call = urllib.request.Request(
                f"{self.server_url}/v1/systemone", data=body,
                headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(call, timeout=self.timeout) as response:
                    result = json.loads(response.read())
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors="replace")[:1000]
                last = ValueError(f"StartLux HTTP {error.code}: {detail}")
                if error.code in (429, 502, 503) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise last from error
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as error:
                last = error
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise
            if set(result.get("answers", {})) != set(request.get("questions", {})):
                raise ValueError("StartLux answer IDs differ from question IDs")
            return dict(result, model=result.get("model", self.model_id))
        raise last

    def native(self, request):
        return self._post(request)

    def native_batch(self, requests, batch_size):
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be positive")
        workers = max(1, min(len(requests), self.concurrency, batch_size))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self._post, requests))
