"""JevLight controller: signal control decisions via the Jev decision model.

Jev is not a chat model.  One request sends a ``state`` plus a map of typed
questions and receives one typed answer per question, evaluated in parallel
against the same state.

JevLight maps signal control onto that interface:

- The **state** is the per-intersection observation in LLMLight semantics
  (queue, three-segment approaching vehicles, average waiting time, occupancy)
  rendered as JSON.  With network packaging every active intersection of the
  road network is packed into one shared state.
- The **question** for each active intersection is one ``Choice`` whose
  criteria are the signal phases available at that intersection, plus one
  speculative ``Noul`` congestion judgment (near-zero cost, evaluated in the
  same pass, used only for logging/analysis).
- The answer's ``choice`` is the phase to activate.  ``probabilities`` and
  ``confidence`` are recorded per decision and can gate a fallback.

Fallbacks follow the migrated ChatLight source conventions: empty junctions
never call the API and use the exact CoLLMLight local ranking; failed or
unparsable requests keep the previous signal (LLMLight/CoLLMLight behavior)
or fall back to the local ranking; answers below ``min_confidence`` take the
same fallback.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Tuple

from jevlight.jev_client import JevClient, JevResult
from jevlight.observation import (
    CONTROLLED_LANES,
    IntersectionObservation,
    canonical_phase_name,
    rank_phases,
)


JEV_PACKAGINGS = ("network", "per_intersection")
JEV_FALLBACKS = ("previous", "ranking")
# Agent modes: ``jevlight`` is this repo's native mapping; ``llmlight`` and
# ``collmlight`` reproduce the request pattern and prompt wording of the two
# migrated ChatLight baselines on the same Jev wire format.
AGENT_MODES = ("jevlight", "llmlight", "collmlight")
PHASE_QUESTION_PREFIX = "phase_"
CONGESTION_QUESTION_PREFIX = "congested_"

# Packaging and speculative-question defaults per agent mode: LLMLight is a
# per-intersection agent with no congestion judgment; CoLLMLight and JevLight
# decide with one network-wide state per step.
AGENT_MODE_DEFAULTS = {
    "jevlight": {"packaging": "network", "speculative": True},
    "llmlight": {"packaging": "per_intersection", "speculative": False},
    "collmlight": {"packaging": "network", "speculative": True},
}


# ---------------------------------------------------------------------- #
# State and question construction
# ---------------------------------------------------------------------- #


def jev_intersection_state(
    observation: IntersectionObservation,
    phase_duration: float,
) -> Dict[str, Any]:
    """Render one intersection observation as a Jev-friendly JSON state.

    The lane semantics follow LLMLight: ``queue`` counts vehicles already
    waiting at the stop line, ``approaching_by_segment`` counts moving
    vehicles in three distance segments (segment 1 nearest the junction).
    """
    lanes: Dict[str, Any] = {}
    for lane_name in CONTROLLED_LANES:
        lane = observation.lanes[lane_name]
        cells = lane.llmlight_cells
        lanes[lane_name] = {
            "queue": int(lane.queue),
            "approaching_by_segment": [
                int(cells[0]),
                int(cells[1]),
                int(cells[2] + cells[3]),
            ],
            "average_waiting_time_s": round(float(lane.avg_wait), 1),
            "occupancy": round(float(lane.occupancy), 3),
        }
    current_phase = (
        canonical_phase_name(observation.current_phase)
        if observation.current_phase
        else None
    )
    duration = (
        int(phase_duration) if float(phase_duration).is_integer() else phase_duration
    )
    return {
        "intersection_id": observation.intersection_id,
        "phase_duration_s": duration,
        "current_phase": current_phase,
        "lanes": lanes,
        "neighbours": list(observation.neighbours),
    }


def phase_criteria(
    observation: IntersectionObservation,
) -> Dict[str, str]:
    """Choice criteria keyed by canonical phase for one intersection."""
    location_words = {
        "N": "northbound (arriving from the south)",
        "S": "southbound (arriving from the north)",
        "E": "eastbound (arriving from the west)",
        "W": "westbound (arriving from the east)",
    }
    movement_words = {"T": "through", "L": "left-turn"}
    criteria: Dict[str, str] = {}
    for phase in observation.phases:
        canonical = canonical_phase_name(phase)
        if canonical in criteria:
            continue
        parts = []
        for index in range(0, len(canonical), 2):
            code = canonical[index : index + 2]
            parts.append(
                f"{code} = {movement_words.get(code[1], code[1])} lanes "
                f"{location_words.get(code[0], code[0])}"
            )
        criteria[canonical] = (
            f"Activates {canonical[:2]} and {canonical[2:]}; "
            f"releases {', '.join(parts)}. Prefer when those lanes hold the "
            "largest combined queue, approaching, and waiting-time pressure."
        )
    return criteria


def phase_question(
    observation: IntersectionObservation,
    phase_duration: float,
    state_path: str,
) -> Dict[str, Any]:
    """The per-intersection phase Choice question in wire format."""
    criteria = phase_criteria(observation)
    duration = (
        int(phase_duration) if float(phase_duration).is_integer() else phase_duration
    )
    instructions = (
        f"At intersection `{state_path}`, choose the signal phase to activate "
        f"for the next {duration} seconds "
        "to most reduce queue pressure and vehicle waiting time. Judge each "
        f"phase option by the lanes it serves in `{state_path}.lanes`: queued "
        "vehicles, approaching vehicles by segment (segment 1 is nearest the "
        "junction), and average waiting time. Heavier queues, more approaching "
        "vehicles, and longer waits on a phase's lanes make that phase the "
        "better choice; the current phase's lanes have already been moving."
    )
    return {
        "type": "choice",
        "instructions": instructions,
        "criteria": criteria,
    }


def llmlight_phase_question(
    observation: IntersectionObservation,
    phase_duration: float,
    state_path: str = "intersection",
) -> Dict[str, Any]:
    """LLMLight-style prompt: one agent per intersection, local view only.

    Wording follows LLMLight's original per-intersection signal-control
    prompt (the intersection's own lanes and current pressure, no network
    context); the wire format stays one Jev ``choice`` question.
    """
    criteria = phase_criteria(observation)
    duration = (
        int(phase_duration) if float(phase_duration).is_integer() else phase_duration
    )
    instructions = (
        f"You are the signal control agent for intersection `{state_path}`. "
        f"The intersection state at `{state_path}` lists every "
        "signal-controlled lane with queued vehicles, approaching vehicles "
        "by distance segment (segment 1 is nearest the junction), and "
        "average waiting time. Select the signal phase to activate for the "
        f"next {duration} seconds to minimize the intersection's queue "
        "length and vehicle waiting time. Movements whose lanes hold "
        "heavier queues, more approaching vehicles, or longer waits need "
        "the green signal sooner; the current phase's lanes have already "
        "been moving."
    )
    return {
        "type": "choice",
        "instructions": instructions,
        "criteria": criteria,
    }


def collmlight_phase_question(
    observation: IntersectionObservation,
    phase_duration: float,
    state_path: str,
    network_size: int,
) -> Dict[str, Any]:
    """CoLLMLight-style prompt: one network-level agent, coordinated view.

    Wording follows CoLLMLight's network-wise signal-control prompt: the
    agent sees the whole road network in one shared state and answers one
    question per intersection, coordinating with neighbouring junctions.
    """
    criteria = phase_criteria(observation)
    duration = (
        int(phase_duration) if float(phase_duration).is_integer() else phase_duration
    )
    instructions = (
        f"You are the network-level signal control agent coordinating "
        f"{network_size} signalized intersections that share one state. For "
        f"intersection `{state_path}`, choose the signal phase to activate "
        f"for the next {duration} seconds to reduce congestion at this "
        "junction and across the network. Judge each phase option by the "
        f"lanes it serves in `{state_path}.lanes` — queued vehicles, "
        "approaching vehicles by segment (segment 1 is nearest the "
        "junction), and average waiting time — while keeping the timing "
        "coordinated with the neighbouring junctions listed under "
        f"`{state_path}.neighbours`. Heavier pressure on a phase's lanes "
        "makes that phase the better choice; the current phase's lanes "
        "have already been moving."
    )
    return {
        "type": "choice",
        "instructions": instructions,
        "criteria": criteria,
    }


def congestion_question(state_path: str) -> Dict[str, Any]:
    """Speculative congestion Noul, logged for analysis (near-zero cost)."""
    return {
        "type": "noul",
        "instructions": (
            f"Is intersection `{state_path}` currently under heavy congestion, "
            "meaning a large share of its signal-controlled lanes hold long "
            "vehicle queues or extreme waiting times?"
        ),
    }


# ---------------------------------------------------------------------- #
# MaxPressure baseline (no decision model)
# ---------------------------------------------------------------------- #


def phase_pressure(observation: IntersectionObservation, phase: str) -> float:
    """Classic max-pressure score of one canonical phase.

    Pressure = queued + approaching vehicles on the two lanes the phase
    serves (LLMLight's MaxPressure semantics, matching the mock Jev's
    ``queue + approaching`` scoring).
    """
    pressure = 0.0
    for lane_name in (phase[:2], phase[2:]):
        lane = observation.lanes[lane_name]
        pressure += float(lane.queue)
        pressure += float(sum(lane.llmlight_cells))
    return pressure


class MaxPressureController:
    """Non-LLM MaxPressure baseline: no Jev, no requests, pure local state.

    Exposes the same ``decide``/``usage_summary`` surface as
    :class:`JevLightController` so the runner's control loop is unchanged;
    every decision is the argmax-pressure phase of the intersection's own
    observation.
    """

    def __init__(self, phase_duration: float):
        self.phase_duration = phase_duration

    @staticmethod
    def _phase_to_action(observation: IntersectionObservation, phase: str) -> int:
        for index, available in enumerate(observation.phases):
            if canonical_phase_name(available) == canonical_phase_name(phase):
                return index
        return 0

    def decide(
        self,
        observations: Sequence[IntersectionObservation],
        step: int,
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
        actions: Dict[str, int] = {}
        traces: List[Dict[str, Any]] = []
        for observation in observations:
            scores: Dict[str, float] = {}
            for phase in observation.phases:
                canonical = canonical_phase_name(phase)
                if canonical not in scores:
                    scores[canonical] = phase_pressure(observation, canonical)
            best = max(sorted(scores), key=scores.get)
            actions[observation.intersection_id] = self._phase_to_action(
                observation, best
            )
            traces.append({
                "step": step,
                "intersection": observation.intersection_id,
                "controller": "maxpressure",
                "agent_mode": "maxpressure",
                "packaging": "none",
                "transport": "local",
                "model": "maxpressure",
                "signal": best,
                "pressures": scores,
                "fallback": None,
            })
        return actions, traces

    def usage_summary(self) -> Dict[str, Any]:
        return {
            "requests": 0,
            "failures": 0,
            "rate_limited": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_mean_s": None,
            "latency_max_s": None,
        }


# ---------------------------------------------------------------------- #
# Controller
# ---------------------------------------------------------------------- #


class JevLightController:
    """LLMLight-style control loop with Jev as the decision model.

    ``decide`` mirrors ``LLMLightController.decide``: observations in, one
    action index per intersection (into ``observation.phases``) and one trace
    record per decision out.  Empty junctions use the exact CoLLMLight local
    ranking without an API call.
    """

    def __init__(
        self,
        client: JevClient,
        phase_duration: float,
        packaging: str = "network",
        fallback: str = "previous",
        min_confidence: float = 0.0,
        speculative: bool = True,
        max_workers: int = 8,
        agent_mode: str = "jevlight",
    ):
        if agent_mode not in AGENT_MODES:
            raise ValueError(
                f"agent_mode must be one of {AGENT_MODES}, got {agent_mode}"
            )
        if packaging not in JEV_PACKAGINGS:
            raise ValueError(
                f"packaging must be one of {JEV_PACKAGINGS}, got {packaging}"
            )
        if fallback not in JEV_FALLBACKS:
            raise ValueError(
                f"fallback must be one of {JEV_FALLBACKS}, got {fallback}"
            )
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        self.client = client
        self.phase_duration = phase_duration
        self.packaging = packaging
        self.fallback = fallback
        self.min_confidence = float(min_confidence)
        self.speculative = speculative
        self.max_workers = max(1, int(max_workers))
        self.agent_mode = agent_mode
        self.previous_signals: Dict[str, str] = {}
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0
        self.total_failures = 0
        self.total_rate_limited = 0
        self.latencies: List[float] = []

    # -- helpers ------------------------------------------------------- #

    def _phase_question(
        self,
        observation: IntersectionObservation,
        state_path: str,
        network_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """The phase Choice question worded for the active agent mode."""
        if self.agent_mode == "llmlight":
            return llmlight_phase_question(
                observation, self.phase_duration, state_path
            )
        if self.agent_mode == "collmlight":
            return collmlight_phase_question(
                observation,
                self.phase_duration,
                state_path,
                network_size or 1,
            )
        return phase_question(observation, self.phase_duration, state_path)

    @staticmethod
    def _phase_to_action(observation: IntersectionObservation, phase: str) -> int:
        for index, available in enumerate(observation.phases):
            if canonical_phase_name(available) == canonical_phase_name(phase):
                return index
        return 0

    def _previous_signal(self, observation: IntersectionObservation) -> str:
        signal = self.previous_signals.get(observation.intersection_id)
        if signal is None and observation.current_phase is not None:
            signal = canonical_phase_name(observation.current_phase)
        available = {
            canonical_phase_name(phase) for phase in observation.phases
        }
        if signal in available:
            return signal
        return canonical_phase_name(observation.phases[0])

    def _fallback_signal(
        self,
        observation: IntersectionObservation,
        reason: str,
    ) -> Tuple[str, str]:
        if self.fallback == "ranking":
            return rank_phases(observation, self.phase_duration)[0][0], reason
        return self._previous_signal(observation), reason

    def _record_result(self, result: JevResult) -> None:
        self.total_requests += 1
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens
        self.latencies.append(result.latency)
        if result.error:
            self.total_failures += 1
        if result.rate_limited:
            self.total_rate_limited += 1

    def _select_signal(
        self,
        observation: IntersectionObservation,
        answer: Optional[Any],
    ) -> Tuple[str, Optional[str], Optional[float], Optional[Dict[str, float]]]:
        """Apply the answer with validity and confidence gating.

        Returns ``(signal, fallback_reason, confidence, probabilities)``.
        ``fallback_reason`` is ``None`` when the Jev answer is used directly.
        """
        if answer is None or answer.get("type") != "choice":
            signal, reason = self._fallback_signal(observation, "missing_answer")
            return signal, reason, None, None
        signal = answer.get("choice")
        probabilities = {
            str(key): float(value)
            for key, value in (answer.get("probabilities") or {}).items()
        }
        confidence = answer.get("confidence")
        confidence_value = (
            float(confidence) if confidence is not None else None
        )
        available = {
            canonical_phase_name(phase) for phase in observation.phases
        }
        if signal not in available:
            fallback_signal, reason = self._fallback_signal(
                observation, "invalid_choice"
            )
            return fallback_signal, reason, confidence_value, probabilities
        if (
            confidence_value is not None
            and confidence_value < self.min_confidence
        ):
            fallback_signal, reason = self._fallback_signal(
                observation, "low_confidence"
            )
            return fallback_signal, reason, confidence_value, probabilities
        return signal, None, confidence_value, probabilities

    def _empty_signal(self, observation: IntersectionObservation) -> str:
        ranking = rank_phases(observation, self.phase_duration)
        return ranking[0][0]

    def _trace_base(
        self,
        observation: IntersectionObservation,
        step: int,
    ) -> Dict[str, Any]:
        return {
            "step": step,
            "intersection": observation.intersection_id,
            "controller": "jevlight",
            "agent_mode": self.agent_mode,
            "packaging": self.packaging,
            "transport": self.client.transport,
            "model": self.client.model or "server-default",
        }

    def _trace_decision(
        self,
        observation: IntersectionObservation,
        step: int,
        question_id: str,
        answer: Optional[Any],
        result: JevResult,
    ) -> Tuple[str, Dict[str, Any]]:
        signal, fallback, confidence, probabilities = self._select_signal(
            observation, answer
        )
        congestion = result.answers.get(
            f"{CONGESTION_QUESTION_PREFIX}{observation.intersection_id}"
        )
        trace = self._trace_base(observation, step)
        trace.update({
            "question_id": question_id,
            "answer": answer,
            "signal": signal,
            "probabilities": probabilities,
            "confidence": confidence,
            "congestion_noul": (
                congestion.get("noul") if congestion else None
            ),
            "fallback": fallback,
            "error": result.error,
            "rate_limited": result.rate_limited,
            "request_latency": result.latency,
            "request_input_tokens": result.input_tokens,
            "request_output_tokens": result.output_tokens,
        })
        return signal, trace

    # -- decision paths ------------------------------------------------ #

    def _decide_network(
        self,
        observations: Sequence[IntersectionObservation],
        active: Sequence[IntersectionObservation],
        step: int,
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
        state: Dict[str, Any] = {
            "scenario": (
                "Traffic signal control. The state holds every signalized "
                "intersection of the road network; each has eight "
                "signal-controlled lanes named like ET (eastbound through) "
                "or WL (westbound left-turn). Right turns are always allowed "
                "and not signalized."
            ),
            "intersections": {
                observation.intersection_id: jev_intersection_state(
                    observation, self.phase_duration
                )
                for observation in observations
            },
        }
        questions: Dict[str, Any] = {}
        for observation in active:
            state_path = f"intersections.{observation.intersection_id}"
            questions[f"{PHASE_QUESTION_PREFIX}{observation.intersection_id}"] = (
                self._phase_question(
                    observation, state_path, network_size=len(observations)
                )
            )
            if self.speculative:
                questions[
                    f"{CONGESTION_QUESTION_PREFIX}{observation.intersection_id}"
                ] = congestion_question(state_path)

        result = self.client.evaluate(state, questions)
        self._record_result(result)
        actions: Dict[str, int] = {}
        traces: List[Dict[str, Any]] = []
        for observation in active:
            question_id = (
                f"{PHASE_QUESTION_PREFIX}{observation.intersection_id}"
            )
            signal, trace = self._trace_decision(
                observation, step, question_id, result.answers.get(question_id), result
            )
            actions[observation.intersection_id] = self._phase_to_action(
                observation, signal
            )
            traces.append(trace)
        return actions, traces

    def _decide_per_intersection(
        self,
        active: Sequence[IntersectionObservation],
        step: int,
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
        requests: List[Tuple[IntersectionObservation, Any, Dict[str, Any]]] = []
        for observation in active:
            state = jev_intersection_state(observation, self.phase_duration)
            questions: Dict[str, Any] = {
                f"{PHASE_QUESTION_PREFIX}{observation.intersection_id}": (
                    self._phase_question(observation, "intersection")
                )
            }
            if self.speculative:
                questions[
                    f"{CONGESTION_QUESTION_PREFIX}{observation.intersection_id}"
                ] = congestion_question("intersection")
            requests.append((observation, state, questions))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(
                executor.map(
                    lambda item: self.client.evaluate(item[1], item[2]),
                    requests,
                )
            )

        actions: Dict[str, int] = {}
        traces: List[Dict[str, Any]] = []
        for (observation, _state, _), result in zip(requests, results):
            self._record_result(result)
            question_id = f"{PHASE_QUESTION_PREFIX}{observation.intersection_id}"
            signal, trace = self._trace_decision(
                observation, step, question_id, result.answers.get(question_id), result
            )
            actions[observation.intersection_id] = self._phase_to_action(
                observation, signal
            )
            traces.append(trace)
        return actions, traces

    def decide(
        self,
        observations: Sequence[IntersectionObservation],
        step: int,
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
        active = [
            observation for observation in observations if not observation.empty
        ]
        actions: Dict[str, int] = {}
        traces: List[Dict[str, Any]] = []

        for observation in observations:
            if observation.empty:
                signal = self._empty_signal(observation)
                actions[observation.intersection_id] = self._phase_to_action(
                    observation, signal
                )
                trace = self._trace_base(observation, step)
                trace.update({
                    "signal": signal,
                    "fallback": "empty_junction_local_ranking",
                })
                traces.append(trace)

        if active:
            if self.packaging == "network":
                active_actions, active_traces = self._decide_network(
                    observations, active, step
                )
            else:
                active_actions, active_traces = self._decide_per_intersection(
                    active, step
                )
            actions.update(active_actions)
            traces.extend(active_traces)

        for observation in observations:
            action = actions[observation.intersection_id]
            signal = next(
                (
                    canonical_phase_name(phase)
                    for index, phase in enumerate(observation.phases)
                    if index == action
                ),
                canonical_phase_name(observation.phases[0]),
            )
            self.previous_signals[observation.intersection_id] = signal
        return actions, traces

    def usage_summary(self) -> Dict[str, Any]:
        latencies = self.latencies
        return {
            "requests": self.total_requests,
            "failures": self.total_failures,
            "rate_limited": self.total_rate_limited,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "latency_mean_s": (
                sum(latencies) / len(latencies) if latencies else None
            ),
            "latency_max_s": max(latencies) if latencies else None,
        }
