"""Inference-time LLMLight and CoLLMLight control on the JevLight SUMO runtime.

The control flow, observation semantics, prompts, parsing and
history/trajectory updates mirror the active inference paths in
``githubs/LLMTSCS`` and ``githubs/CoLLMLight``; invalid CoLLMLight responses
keep the previous phase by design.

Implementation notes:

- the observation layer (``LaneObservation``/``IntersectionObservation``,
  ``collect_observations``, ``rank_phases``, the lane constants) is JevLight's
  own ``jevlight.observation``, so every controller here consumes JevLight
  observations unchanged;
- the generic LLM fallback is the ``baselines.llmlight.language_models``
  client, and the adapter accepts ``llm_base_url``/``llm_api_key`` overrides
  for it;
- ``BaseLLMLightController`` carries the ``usage_summary`` surface the
  JevLight runner contract requires on top of the raw token counters.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from jevlight.observation import (
    CANONICAL_PHASES,
    CONTROLLED_LANES,
    IntersectionObservation,
    LaneObservation,
    canonical_phase_name,
    phase_lanes,
    rank_phases,
)

from baselines.llmlight.prompts import (
    LLMLIGHT_SYSTEM_PROMPT,
    collmlight_atr_prompt,
    collmlight_reactive_prompt,
    collmlight_system_prompt,
    llmlight_alpaca_prompt,
    llmlight_state2text,
    llmlight_user_prompt,
    local_signal_priority,
)


DEFAULT_BACKBONE = "deepseek-v4-flash"
DEFAULT_LLM_PATH = "siliconflow/deepseek-ai/DeepSeek-V4-Flash"
DEFAULT_LLMLIGHT_MODEL = "LLMLight"
DEFAULT_LLMLIGHT_BASE_URL = "http://localhost:8001/v1"
DEFAULT_LLMLIGHT_TOKENIZER_PATH = "/path/to/llm_models/llama"
DEFAULT_LLMLIGHT_MAX_CONTEXT_TOKENS = 4 * 1024
LLMLIGHT_PROVIDERS = ("local", "siliconflow")
TRAJECTORY_CONNECTION_THRESHOLD = 0.05


def resolve_llmlight_model(provider: str, model: str) -> str:
    """Resolve a user-facing LLMLight model ID for the selected backend."""
    if provider == "local":
        return model
    if provider != "siliconflow":
        raise ValueError(f"Unsupported LLMLight provider: {provider}")
    if model == DEFAULT_LLMLIGHT_MODEL:
        return DEFAULT_LLM_PATH
    if model.startswith("siliconflow/"):
        return model
    return f"siliconflow/{model}"


@dataclass
class LLMResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency: float = 0.0
    error: Optional[str] = None
    request_max_tokens: Optional[int] = None


class LanguageModelAdapter:
    """Route LLMLight, CoLLMLight, and generic inference backends."""

    def __init__(
        self,
        model: str = DEFAULT_BACKBONE,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        top_p: float = 1.0,
        batch_size: int = 8,
        mock: bool = False,
        llmlight_base_url: Optional[str] = None,
        llmlight_api_key: Optional[str] = None,
        llmlight_tokenizer_path: Optional[str] = None,
        llmlight_max_context_tokens: int = DEFAULT_LLMLIGHT_MAX_CONTEXT_TOKENS,
        llm_base_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
    ):
        self.model = model
        self.mock = mock
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.batch_size = max(1, batch_size)
        self.llm_path = self._resolve_llm_path(model)
        self._backend = None
        self._llmlight_base_url = (
            llmlight_base_url.rstrip("/") if llmlight_base_url else None
        )
        self._llmlight_api_key = llmlight_api_key or "EMPTY"
        self._llmlight_tokenizer = None
        self._llmlight_max_context_tokens = int(llmlight_max_context_tokens)
        self.prompt_format = (
            "llmlight_alpaca_completion"
            if self._llmlight_base_url is not None
            else "chat_messages"
        )
        self._collmlight_tokenizer = None
        self._collmlight_base_url = None
        self._collmlight_api_key = None
        self._collmlight_model = None
        self._collmlight_max_context_tokens = None
        self._collmlight_template_margin_tokens = None
        self._init_llmlight_dynamic_budget(llmlight_tokenizer_path)
        self._init_collmlight_dynamic_budget()
        if not mock:
            if (
                self._llmlight_base_url is None
                and self._collmlight_tokenizer is None
            ):
                from baselines.llmlight.language_models import LLM

                self._backend = LLM(
                    llm_path=self.llm_path,
                    batch_size=self.batch_size,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    fixed_max_tokens=True,
                    retry_sleep_seconds=3.0,
                    enable_thinking=False,
                    max_retries=3,
                    base_url=llm_base_url,
                    api_key=llm_api_key,
                )

    def _init_llmlight_dynamic_budget(
        self,
        tokenizer_path: Optional[str],
    ) -> None:
        if self.mock or self._llmlight_base_url is None or not tokenizer_path:
            return
        if self._llmlight_max_context_tokens <= 1:
            raise ValueError(
                "LLMLight max context tokens must be greater than one"
            )

        path = Path(tokenizer_path).expanduser()
        tokenizer_json = path if path.is_file() else path / "tokenizer.json"
        if not tokenizer_json.is_file():
            raise FileNotFoundError(
                "LLMLight tokenizer.json does not exist: "
                f"{tokenizer_json}"
            )

        from tokenizers import Tokenizer

        self._llmlight_tokenizer = Tokenizer.from_file(str(tokenizer_json))

    def _llmlight_request_budget(self, prompt: str) -> Tuple[int, int]:
        if self._llmlight_tokenizer is None:
            return 0, self.max_tokens

        prompt_tokens = len(self._llmlight_tokenizer.encode(prompt).ids)
        available_tokens = self._llmlight_max_context_tokens - prompt_tokens
        if available_tokens <= 0:
            raise ValueError(
                "LLMLight prompt exceeds its context budget: "
                f"prompt_tokens={prompt_tokens}, "
                f"max_context_tokens={self._llmlight_max_context_tokens}"
            )
        return prompt_tokens, min(self.max_tokens, available_tokens)

    def _complete_llmlight(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResult:
        """Call a served LLMLight checkpoint as a raw text completion.

        This intentionally uses ``/completions`` instead of
        ``/chat/completions``.  The checkpoint was trained on the flattened
        Alpaca prompt produced by :func:`llmlight_alpaca_prompt`; applying the
        server's chat template on top would change the model input.
        """
        import requests

        started = time.time()
        prompt = llmlight_alpaca_prompt(system_prompt, user_prompt)
        request_max_tokens = None
        try:
            _, request_max_tokens = self._llmlight_request_budget(prompt)
            response = requests.post(
                f"{self._llmlight_base_url}/completions",
                headers={
                    "Authorization": f"Bearer {self._llmlight_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.llm_path,
                    "prompt": prompt,
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "max_tokens": request_max_tokens,
                    "stream": False,
                },
                timeout=180,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["text"]
            usage = payload.get("usage") or {}
            return LLMResult(
                content=str(content or ""),
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                latency=time.time() - started,
                request_max_tokens=request_max_tokens,
            )
        except Exception as exc:
            return LLMResult(
                content="",
                latency=time.time() - started,
                error=f"{type(exc).__name__}: {exc}",
                request_max_tokens=request_max_tokens,
            )

    def _init_collmlight_dynamic_budget(self) -> None:
        tokenizer_path = os.environ.get("COLLMLIGHT_TOKENIZER_JSON")
        if self.mock or not tokenizer_path:
            return
        if "collmlight" not in self.llm_path.lower():
            return

        path = Path(tokenizer_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"CoLLMLight tokenizer.json does not exist: {path}"
            )
        from tokenizers import Tokenizer

        max_context_tokens = int(
            os.environ.get("COLLMLIGHT_MAX_CONTEXT_TOKENS", "8192")
        )
        template_margin = int(
            os.environ.get("COLLMLIGHT_CHAT_TEMPLATE_MARGIN_TOKENS", "128")
        )
        if max_context_tokens <= 1:
            raise ValueError("COLLMLIGHT_MAX_CONTEXT_TOKENS must be greater than one")
        if template_margin < 0 or template_margin >= max_context_tokens:
            raise ValueError(
                "COLLMLIGHT_CHAT_TEMPLATE_MARGIN_TOKENS must be non-negative "
                "and smaller than COLLMLIGHT_MAX_CONTEXT_TOKENS"
            )

        self._collmlight_tokenizer = Tokenizer.from_file(str(path))
        self._collmlight_base_url = os.environ.get(
            "LOCAL_LLM_BASE_URL", "http://localhost:8000/v1"
        ).rstrip("/")
        self._collmlight_api_key = os.environ.get("LOCAL_LLM_API_KEY", "EMPTY")
        self._collmlight_model = self.llm_path.rsplit("/", 1)[-1]
        self._collmlight_max_context_tokens = max_context_tokens
        self._collmlight_template_margin_tokens = template_margin

    def _collmlight_request_budget(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Tuple[int, int]:
        content_tokens = len(self._collmlight_tokenizer.encode(system_prompt).ids)
        content_tokens += len(self._collmlight_tokenizer.encode(user_prompt).ids)
        estimated_input_tokens = (
            content_tokens + self._collmlight_template_margin_tokens
        )
        available_tokens = (
            self._collmlight_max_context_tokens - estimated_input_tokens
        )
        if available_tokens <= 0:
            raise ValueError(
                "CoLLMLight prompt exceeds its context budget: "
                f"estimated_input_tokens={estimated_input_tokens}, "
                f"max_context_tokens={self._collmlight_max_context_tokens}"
            )
        return estimated_input_tokens, min(self.max_tokens, available_tokens)

    def _complete_collmlight(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResult:
        import requests

        started = time.time()
        request_max_tokens = None
        try:
            _, request_max_tokens = self._collmlight_request_budget(
                system_prompt,
                user_prompt,
            )
            response = requests.post(
                f"{self._collmlight_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._collmlight_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._collmlight_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "max_tokens": request_max_tokens,
                    "stream": False,
                    "enable_thinking": False,
                },
                timeout=180,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage") or {}
            return LLMResult(
                content=str(content or ""),
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                latency=time.time() - started,
                request_max_tokens=request_max_tokens,
            )
        except Exception as exc:
            return LLMResult(
                content="",
                latency=time.time() - started,
                error=f"{type(exc).__name__}: {exc}",
                request_max_tokens=request_max_tokens,
            )

    @staticmethod
    def _resolve_llm_path(model: str) -> str:
        normalized = model.strip().lower().replace("_", "-")
        if normalized in {"deepseek-v4-flash", "deepseek-v4flash"}:
            return DEFAULT_LLM_PATH
        return model

    @staticmethod
    def _mock_response(user_prompt: str) -> str:
        priority_match = re.search(
            r"\|1\|(ETWT|NTST|ELWL|NLSL)\|", user_prompt, re.IGNORECASE
        )
        signal = priority_match.group(1).upper() if priority_match else "ETWT"
        if "structured JSON format" in user_prompt:
            return json.dumps(
                {"signal": signal, "reason": "mock priority selection", "used_atr": 0}
            )
        if "Advance Traffic Reasoning" in user_prompt:
            return "## Identify Critical Lanes\nNone\n\n## Summary\nUse local demand."
        return f"Traffic demand favors this phase. <signal>{signal}</signal>"

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResult:
        started = time.time()
        if self.mock:
            return LLMResult(
                content=self._mock_response(user_prompt),
                latency=time.time() - started,
            )
        if self._llmlight_base_url is not None:
            return self._complete_llmlight(system_prompt, user_prompt)
        if self._collmlight_tokenizer is not None:
            return self._complete_collmlight(system_prompt, user_prompt)
        try:
            content = self._backend.inference(user_prompt, system_prompt=system_prompt)
        except Exception as exc:
            return LLMResult(
                content="",
                latency=time.time() - started,
                error=f"{type(exc).__name__}: {exc}",
            )
        if content:
            return LLMResult(content=str(content), latency=time.time() - started)
        return LLMResult(
            content="",
            latency=time.time() - started,
            error="language_models.LLM.inference returned an empty response",
        )

    def batch_complete(
        self,
        system_prompt: str,
        prompts: Sequence[str],
    ) -> List[LLMResult]:
        if not prompts:
            return []
        if self.mock:
            return [self.complete(system_prompt, prompt) for prompt in prompts]
        if self._llmlight_base_url is not None:
            with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
                return list(
                    executor.map(
                        lambda prompt: self._complete_llmlight(
                            system_prompt,
                            prompt,
                        ),
                        prompts,
                    )
                )
        if self._collmlight_tokenizer is not None:
            with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
                return list(
                    executor.map(
                        lambda prompt: self._complete_collmlight(
                            system_prompt,
                            prompt,
                        ),
                        prompts,
                    )
                )

        started = time.time()
        try:
            responses = self._backend.batch_inference(
                list(prompts), system_prompt=system_prompt
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            return [
                LLMResult(content="", latency=time.time() - started, error=error)
                for _ in prompts
            ]

        elapsed = time.time() - started
        results: List[LLMResult] = []
        for index in range(len(prompts)):
            content = responses[index] if index < len(responses) else None
            results.append(
                LLMResult(
                    content=str(content) if content else "",
                    latency=elapsed,
                    error=(
                        None
                        if content
                        else "language_models.LLM.batch_inference returned an empty response"
                    ),
                )
            )
        return results


def extract_signal(response: str, phases: Sequence[str] = CANONICAL_PHASES) -> Optional[str]:
    """LLMLight's exact last-tag parser, exposed for compatibility."""
    signals = re.findall(r"<signal>(.*?)</signal>", response or "")
    signal = signals[-1] if signals else None
    return signal if signal in phases else None


def extract_collmlight_result(response: str) -> Dict[str, Any]:
    """CoLLMLight's markdown-aware, case-insensitive JSON parser."""
    try:
        json_data = None
        match = re.search(r"```json\s*({.*?})\s*```", response or "", re.DOTALL)
        if match:
            json_data = match.group(1)
        else:
            match = re.search(r"({.*})", (response or "").strip(), re.DOTALL)
            if match:
                json_data = match.group(1)
        if json_data:
            data = json.loads(json_data)
            lowered = {str(key).lower(): value for key, value in data.items()}
            return {
                "signal": lowered.get("signal"),
                "reason": lowered.get("reason"),
                "used_atr": lowered.get("used_atr", 0),
            }
    except Exception:
        pass
    return {"signal": None, "reason": None, "used_atr": 0}


def _after_think_tag(text: str) -> str:
    tag = "</think>"
    if tag in (text or ""):
        return text.split(tag, 1)[1].strip()
    return text or ""


class BaseLLMLightController:
    def __init__(self, llm: LanguageModelAdapter, phase_duration: float):
        self.llm = llm
        self.phase_duration = phase_duration
        self.total_requests = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_failures = 0
        self.latencies: List[float] = []
        self.previous_signals: Dict[str, str] = {}

    @staticmethod
    def _phase_to_action(observation: IntersectionObservation, phase: str) -> int:
        for index, available in enumerate(observation.phases):
            if canonical_phase_name(available) == canonical_phase_name(phase):
                return index
        return 0

    def _record_usage(self, result: LLMResult) -> None:
        self.total_requests += 1
        self.total_prompt_tokens += result.prompt_tokens
        self.total_completion_tokens += result.completion_tokens
        self.latencies.append(float(result.latency or 0.0))
        if result.error:
            self.total_failures += 1

    def _previous_signal(self, observation: IntersectionObservation) -> str:
        signal = self.previous_signals.get(observation.intersection_id)
        if signal is None and observation.current_phase is not None:
            signal = canonical_phase_name(observation.current_phase)
        return signal if signal in CANONICAL_PHASES else "ETWT"

    def usage_summary(self) -> Dict[str, Any]:
        """JevLight runner usage surface (the source only carried counters)."""
        latencies = [latency for latency in self.latencies if latency >= 0]
        return {
            "requests": self.total_requests,
            "failures": self.total_failures,
            "rate_limited": 0,
            "input_tokens": self.total_prompt_tokens,
            "output_tokens": self.total_completion_tokens,
            "latency_mean_s": (
                sum(latencies) / len(latencies) if latencies else None
            ),
            "latency_max_s": max(latencies) if latencies else None,
        }

    def decide(
        self,
        observations: Sequence[IntersectionObservation],
        step: int,
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
        raise NotImplementedError


class LLMLightController(BaseLLMLightController):
    """Exact open-LLM inference controller from the LLMLight repository."""

    def decide(self, observations, step):
        prompts = [
            llmlight_user_prompt(llmlight_state2text(observation.lanes))
            for observation in observations
        ]
        results = self.llm.batch_complete(LLMLIGHT_SYSTEM_PROMPT, prompts)
        actions: Dict[str, int] = {}
        traces: List[Dict[str, Any]] = []
        for observation, prompt, result in zip(observations, prompts, results):
            self._record_usage(result)
            parsed_signal = extract_signal(result.content)
            if parsed_signal is not None:
                signal = parsed_signal
                fallback = None
            elif result.error:
                signal = self._previous_signal(observation)
                fallback = "previous_signal_after_request_failure"
            else:
                signal = "ETWT"
                fallback = "ETWT"
            actions[observation.intersection_id] = self._phase_to_action(
                observation, signal
            )
            self.previous_signals[observation.intersection_id] = signal
            traces.append({
                "step": step,
                "intersection": observation.intersection_id,
                "controller": "llmlight",
                "agent_mode": "llmlight",
                "packaging": "per_intersection",
                "system_prompt": LLMLIGHT_SYSTEM_PROMPT,
                "prompt": prompt,
                "prompt_format": getattr(self.llm, "prompt_format", "chat_messages"),
                "response": result.content,
                "error": result.error,
                "latency": result.latency,
                "request_max_tokens": result.request_max_tokens,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "fallback": fallback,
                "signal": signal,
            })
        return actions, traces


def _empty_connection_memory() -> Dict[str, Any]:
    return {
        "from_count": {},
        "to_count": {},
        "upstream_lanes": [],
        "downstream_lanes": [],
    }


class CoLLMLightController(BaseLLMLightController):
    """Exact active CoLLMLight ATR→Reactive Action inference flow."""

    def __init__(
        self,
        llm: LanguageModelAdapter,
        phase_duration: float,
        history_window: int = 5,
        communication_threshold: float = 0.0,
        disable_psr: bool = False,
    ):
        super().__init__(llm, phase_duration)
        self.history_window = max(0, history_window)
        self.communication_threshold = communication_threshold
        self.disable_psr = disable_psr
        self.system_prompt = collmlight_system_prompt(phase_duration)
        self.previous_observations: Dict[str, IntersectionObservation] = {}
        self.traffic_state_logs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.vehicle_last_release: Dict[str, Tuple[int, str]] = {}
        self.connection_memory: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(
            lambda: {
                lane: _empty_connection_memory() for lane in CONTROLLED_LANES
            }
        )
        self.lane_activation_memories: Dict[
            str, Dict[str, List[Dict[str, Any]]]
        ] = defaultdict(lambda: {lane: [] for lane in CONTROLLED_LANES})
        self.release_vehicle_to_memory: Dict[
            str, Tuple[str, str, int]
        ] = {}

    @staticmethod
    def _vehicle_changes(
        previous: IntersectionObservation,
        current: IntersectionObservation,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        released: Dict[str, List[str]] = {}
        entered: Dict[str, List[str]] = {}
        for lane in CONTROLLED_LANES:
            before = list(previous.lanes[lane].vehicles)
            now = list(current.lanes[lane].vehicles)
            before_set = set(before)
            now_set = set(now)
            released[lane] = [vehicle for vehicle in before if vehicle not in now_set]
            entered[lane] = [vehicle for vehicle in now if vehicle not in before_set]
        return released, entered

    @staticmethod
    def _lane_traffic_state(
        previous: LaneObservation,
        current: LaneObservation,
    ) -> Dict[str, Any]:
        before_vehicles = set(previous.vehicles)
        current_vehicles = set(current.vehicles)
        queued_before = previous.queue
        queued_current = current.queue
        moving_before = sum(previous.cells)
        moving_current = sum(current.cells)
        wait_before = round(previous.avg_wait / 60, 2)
        wait_current = round(current.avg_wait / 60, 2)
        occupancy_before = round(previous.occupancy * 100, 2)
        occupancy_current = round(current.occupancy * 100, 2)
        return {
            "Cars Input": len(current_vehicles - before_vehicles),
            "Cars Output": len(before_vehicles - current_vehicles),
            "Queued Cars Change": queued_current - queued_before,
            "Queued Cars": queued_current,
            "Moving Cars Change": moving_current - moving_before,
            "Moving Cars": moving_current,
            "Average Waiting Time Change (mins)": round(
                wait_current - wait_before, 2
            ),
            "Average Waiting Time (mins)": wait_current,
            "Occupancy Change (%)": round(
                occupancy_current - occupancy_before, 2
            ),
            "Occupancy (%)": occupancy_current,
        }

    def _remember_activation(
        self,
        intersection_id: str,
        signal: str,
        previous: IntersectionObservation,
        released: Mapping[str, List[str]],
    ) -> None:
        for lane in phase_lanes(signal):
            if lane not in CONTROLLED_LANES:
                continue
            lane_before = previous.lanes[lane]
            if lane_before.occupancy == 0:
                continue
            memory = {
                "lane": lane,
                "occupancy_before": lane_before.occupancy,
                "queue_num_before": lane_before.queue,
                "moving_num_before": sum(lane_before.cells),
                "release_results": {vehicle: None for vehicle in released[lane]},
                "let_downstream_over100": False,
            }
            memory_index = len(self.lane_activation_memories[intersection_id][lane])
            self.lane_activation_memories[intersection_id][lane].append(memory)
            for vehicle in released[lane]:
                self.release_vehicle_to_memory[vehicle] = (
                    intersection_id,
                    lane,
                    memory_index,
                )

    def _update_connections(
        self,
        observations: Sequence[IntersectionObservation],
        released_by_index: Mapping[int, Mapping[str, List[str]]],
        entered_by_index: Mapping[int, Mapping[str, List[str]]],
    ) -> None:
        for intersection_index, released in released_by_index.items():
            for lane, vehicles in released.items():
                for vehicle in vehicles:
                    self.vehicle_last_release[vehicle] = (intersection_index, lane)

        for intersection_index, entered in entered_by_index.items():
            for lane, vehicles in entered.items():
                downstream = (intersection_index, lane)
                downstream_id = observations[intersection_index].intersection_id
                for vehicle in vehicles:
                    upstream = self.vehicle_last_release.get(vehicle)
                    if upstream is None:
                        continue
                    upstream_index, upstream_lane = upstream
                    upstream_id = observations[upstream_index].intersection_id
                    upstream_memory = self.connection_memory[upstream_id][upstream_lane]
                    downstream_memory = self.connection_memory[downstream_id][lane]
                    upstream_memory["to_count"][downstream] = (
                        upstream_memory["to_count"].get(downstream, 0) + 1
                    )
                    downstream_memory["from_count"][upstream] = (
                        downstream_memory["from_count"].get(upstream, 0) + 1
                    )
                    activation_ref = self.release_vehicle_to_memory.get(vehicle)
                    if activation_ref:
                        memory_intersection, memory_lane, memory_index = activation_ref
                        self.lane_activation_memories[memory_intersection][memory_lane][
                            memory_index
                        ]["release_results"][vehicle] = downstream

        for observation in observations:
            for lane in CONTROLLED_LANES:
                memory = self.connection_memory[observation.intersection_id][lane]
                for count_key, lanes_key in (
                    ("from_count", "upstream_lanes"),
                    ("to_count", "downstream_lanes"),
                ):
                    counts = memory[count_key]
                    total = sum(counts.values())
                    memory[lanes_key] = [
                        candidate
                        for candidate, count in counts.items()
                        if total and count / total > TRAJECTORY_CONNECTION_THRESHOLD
                    ]

    @staticmethod
    def _summary(record: Mapping[str, Any]) -> Dict[str, Any]:
        values = [value for key, value in record.items() if key != "Signal"]
        return {
            "Total Cars Output": sum(value["Cars Output"] for value in values),
            "Over Occupancy": any(value["Occupancy (%)"] >= 100 for value in values),
            "Average Queued Length": round(
                sum(value["Queued Cars"] for value in values) / len(values), 2
            ),
            "Max Average Waiting Time": max(
                value["Average Waiting Time (mins)"] for value in values
            ),
        }

    def _update_transition_history(
        self,
        observations: Sequence[IntersectionObservation],
    ) -> None:
        released_by_index: Dict[int, Dict[str, List[str]]] = {}
        entered_by_index: Dict[int, Dict[str, List[str]]] = {}
        transition_records: Dict[int, Dict[str, Any]] = {}

        for index, current in enumerate(observations):
            previous = self.previous_observations.get(current.intersection_id)
            if previous is None:
                continue
            released, entered = self._vehicle_changes(previous, current)
            released_by_index[index] = released
            entered_by_index[index] = entered
            previous_signal = self.previous_signals.get(current.intersection_id)
            if previous_signal is None:
                continue
            self._remember_activation(
                current.intersection_id,
                previous_signal,
                previous,
                released,
            )
            record: Dict[str, Any] = {"Signal": previous_signal}
            for lane in CONTROLLED_LANES:
                record[lane] = self._lane_traffic_state(
                    previous.lanes[lane], current.lanes[lane]
                )
            transition_records[index] = record

        self._update_connections(observations, released_by_index, entered_by_index)

        for index, record in transition_records.items():
            current = observations[index]
            local_memory = self.connection_memory[current.intersection_id]
            for lane in CONTROLLED_LANES:
                for relation, candidates_key in (
                    ("upstream", "upstream_lanes"),
                    ("downstream", "downstream_lanes"),
                ):
                    for other_index, other_lane in local_memory[lane][candidates_key]:
                        other_current = observations[other_index]
                        if (
                            other_current.lanes[other_lane].occupancy
                            <= self.communication_threshold
                        ):
                            continue
                        other_previous = self.previous_observations.get(
                            other_current.intersection_id
                        )
                        if other_previous is None:
                            continue
                        name = f"{lane}'s {relation} lane ({other_index}, {other_lane})"
                        record[name] = self._lane_traffic_state(
                            other_previous.lanes[other_lane],
                            other_current.lanes[other_lane],
                        )
            record["Summary"] = self._summary(record)
            self.traffic_state_logs[current.intersection_id].append(record)

    def _historical_observation(self, intersection_id: str, timestep: int) -> str:
        history = self.traffic_state_logs[intersection_id]
        if self.history_window == 0:
            return ""
        history_state = history[-self.history_window - 1 : -1]
        timestep_start = timestep - len(history_state)
        text = "## Historical Observation\n"
        text += "- Lanes include both signal-controlled lanes at the current intersection (e.g., NL, NT, SL, ST, EL, ET, WL, WT) and upstream/downstream lanes from neighboring intersections (e.g., SL's upstream lane (4, ST)). **Only lanes with vehicles are shown.**\n"
        text += "- Values are shown as: value or value(+change from previous timestep).\n\n"
        for index, record in enumerate(history_state):
            text += f"Timestep {timestep_start + index} signal: {record['Signal']}\n"
            text += f"Timestep {timestep_start + index + 1} traffic states:\n"
            text += "|Lane|Cars Input|Cars Output|Queued Cars|Moving Cars|Average Waiting Time (mins)|Occupancy (%)|\n"
            text += self._traffic_rows(record)
            text += "\n"
        return text

    @staticmethod
    def _traffic_rows(record: Mapping[str, Any]) -> str:
        text = ""
        for lane, data in record.items():
            if lane in {"Signal", "Summary"}:
                continue
            exists = data["Occupancy (%)"] + data["Cars Input"] + data["Cars Output"]
            if not exists:
                continue
            text += (
                f"|{lane}|{int(data['Cars Input'])}|{int(data['Cars Output'])}|"
                f"{int(data['Queued Cars'])}"
                f"({'+' if data['Queued Cars Change'] >= 0 else ''}{int(data['Queued Cars Change'])})|"
                f"{int(data['Moving Cars'])}"
                f"({'+' if data['Moving Cars Change'] >= 0 else ''}{int(data['Moving Cars Change'])})|"
                f"{data['Average Waiting Time (mins)']}"
                f"({'+' if data['Average Waiting Time Change (mins)'] >= 0 else ''}{data['Average Waiting Time Change (mins)']})|"
                f"{data['Occupancy (%)']}"
                f"({'+' if data['Occupancy Change (%)'] >= 0 else ''}{data['Occupancy Change (%)']})|\n"
            )
        return text

    def _latest_traffic_record(
        self, observation: IntersectionObservation
    ) -> Dict[str, Any]:
        """Latest transition record, or a zero-change snapshot on first sight.

        The very first decision step has no previous observation, so no
        transition record exists yet (networks can already have
        vehicles on controlled lanes at that point).  Present the current
        snapshot as a record whose changes are all zero instead of crashing.
        """
        history = self.traffic_state_logs.get(observation.intersection_id)
        if history:
            return history[-1]
        record: Dict[str, Any] = {"Signal": self._previous_signal(observation)}
        for lane in CONTROLLED_LANES:
            current_lane = observation.lanes[lane]
            record[lane] = self._lane_traffic_state(current_lane, current_lane)
        return record

    def _atr_prompt(self, observation: IntersectionObservation, step: int) -> str:
        latest = self._latest_traffic_record(observation)
        historical = self._historical_observation(
            observation.intersection_id, step - 1
        )
        current = "## Current Observation\n"
        current += f"Timestep {step - 1} signal: {latest['Signal']}\n"
        return collmlight_atr_prompt(step - 1, step, historical, current)

    def _reactive_prompt(
        self,
        observation: IntersectionObservation,
        ranking: Sequence[Tuple[str, float]],
        atr_result: str,
        step: int,
    ) -> str:
        latest = self._latest_traffic_record(observation)
        current = "# Current Observation\n"
        current += "- Lanes include both signal-controlled lanes at the current intersection (e.g., NL, NT, SL, ST, EL, ET, WL, WT) and upstream/downstream lanes from neighboring intersections (e.g., SL's upstream lane (4, ST)). **Only lanes with vehicles are shown.**\n"
        current += "- Values are shown as: value or value(+change from previous timestep).\n\n"
        current += f"Timestep {step - 1} signal: {latest['Signal']}\n"
        current += f"Timestep {step} traffic states:\n"
        current += "|Lane|Cars Input|Cars Output|Queued Cars|Moving Cars|Average Waiting Time (mins)|Occupancy (%)|\n"
        current += self._traffic_rows(latest)
        current += "\n"
        return collmlight_reactive_prompt(
            step - 1,
            step,
            atr_result,
            current,
            local_signal_priority(ranking),
        )

    def _commit_step(
        self,
        observations: Sequence[IntersectionObservation],
        actions: Mapping[str, int],
    ) -> None:
        for observation in observations:
            action = actions[observation.intersection_id]
            signal = next(
                (
                    canonical_phase_name(phase)
                    for index, phase in enumerate(observation.phases)
                    if index == action
                ),
                "ETWT",
            )
            self.previous_signals[observation.intersection_id] = signal
            self.previous_observations[observation.intersection_id] = observation

    def decide(self, observations, step):
        self._update_transition_history(observations)
        actions: Dict[str, int] = {}
        traces: List[Dict[str, Any]] = []
        active: List[Tuple[IntersectionObservation, List[Tuple[str, float]]]] = []

        for observation in observations:
            if observation.empty:
                # The source's empty-junction path always uses 11.11 m/s.
                ranking = rank_phases(observation, self.phase_duration)
                signal = ranking[0][0]
                actions[observation.intersection_id] = self._phase_to_action(
                    observation, signal
                )
            else:
                # Match IntersectionAgent.estimate_effective_range(): its sole
                # network-specific inference rule uses 16.67 m/s for 33 nodes.
                car_speed = 16.67 if len(observations) == 33 else 11.11
                ranking = rank_phases(
                    observation,
                    self.phase_duration,
                    car_speed=car_speed,
                )
                active.append((observation, ranking))

        if not active:
            self._commit_step(observations, actions)
            return actions, traces

        atr_prompts = [
            self._atr_prompt(observation, step) for observation, _ in active
        ]
        if self.disable_psr:
            atr_results = [LLMResult(content="") for _ in atr_prompts]
        else:
            atr_results = self.llm.batch_complete(
                self.system_prompt, atr_prompts
            )
            for result in atr_results:
                result.content = _after_think_tag(result.content)
                self._record_usage(result)

        reactive_prompts = [
            self._reactive_prompt(observation, ranking, atr_result.content, step)
            for (observation, ranking), atr_result in zip(active, atr_results)
        ]
        reactive_results = self.llm.batch_complete(
            self.system_prompt, reactive_prompts
        )

        for (
            (observation, ranking),
            atr_prompt,
            atr_result,
            reactive_prompt,
            reactive_result,
        ) in zip(
            active,
            atr_prompts,
            atr_results,
            reactive_prompts,
            reactive_results,
        ):
            self._record_usage(reactive_result)
            parsed = extract_collmlight_result(reactive_result.content)
            if parsed["signal"] in CANONICAL_PHASES:
                signal = parsed["signal"]
                fallback = None
            else:
                signal = self._previous_signal(observation)
                fallback = (
                    "previous_signal_after_request_failure"
                    if reactive_result.error
                    else "previous_signal_after_invalid_response"
                )
            actions[observation.intersection_id] = self._phase_to_action(
                observation, signal
            )
            latest = self._latest_traffic_record(observation)
            communicated = any(
                key not in {*CONTROLLED_LANES, "Signal", "Summary"}
                for key in latest
            )
            traces.append({
                "step": step,
                "intersection": observation.intersection_id,
                "controller": "collmlight",
                "agent_mode": "collmlight",
                "packaging": "per_intersection",
                "communicated": communicated,
                "system_prompt": self.system_prompt,
                "atr_prompt": atr_prompt,
                "atr_response": atr_result.content,
                "atr_error": atr_result.error,
                "atr_latency": atr_result.latency,
                "atr_request_max_tokens": atr_result.request_max_tokens,
                "reactive_prompt": reactive_prompt,
                "reactive_response": reactive_result.content,
                "reactive_error": reactive_result.error,
                "reactive_latency": reactive_result.latency,
                "reactive_request_max_tokens": reactive_result.request_max_tokens,
                "reason": parsed["reason"],
                "used_atr": parsed["used_atr"],
                "fallback": fallback,
                "signal": signal,
            })

        self._commit_step(observations, actions)
        return actions, traces
