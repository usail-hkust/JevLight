"""MaxPressure baseline: strict lane-pressure policy.

This is not JevLight's built-in ``--dry_run`` controller.  Per phase, the
score is the sum over the phase's movements of (upstream queue − downstream
queue); the best-scoring phase wins and ties keep the earlier phase.

Upstream is the intersection's own incoming movement queue.  The downstream
queue is read from the receiving movement lanes at the downstream junctions
through ``IntersectionObservation.lane_relations`` (built from SUMO lane
connections).  Implementation notes: the downstream aggregate is per
destination movement rather than per de-duplicated physical lane, and when
the road topology is unavailable the score degrades to upstream-only.  Every
trace records the per-movement upstream/downstream values and
``topology_available`` so runs are auditable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from jevlight.observation import (
    CONTROLLED_LANES,
    IntersectionObservation,
    canonical_phase_name,
    phase_lanes,
)


class StrictLaneMaxPressureController:
    """Strict lane-pressure MaxPressure on the JevLight controller contract."""

    def __init__(self, phase_duration: float):
        self.phase_duration = phase_duration

    @staticmethod
    def _upstream_downstream(
        observation: IntersectionObservation,
        by_id: Dict[str, IntersectionObservation],
    ) -> Tuple[Dict[str, float], Dict[str, float], bool]:
        """Movement-level queues, mirroring the source's graph semantics.

        With topology available, only movements that feed another junction
        contribute (an edge to a downstream junction exists for them, exactly
        like the source's ``intersection_graph.successors`` loop); boundary
        movements that exit the network contribute nothing.  Without topology
        the score degrades to upstream-only over the controlled lanes.
        """
        upstream: Dict[str, float] = {}
        downstream: Dict[str, float] = {}
        topology_available = bool(observation.topology_available and observation.lane_relations)
        if topology_available:
            for movement, relations in observation.lane_relations.items():
                refs = relations.get("downstream") or []
                if not refs:
                    continue
                upstream[movement] = float(observation.lanes[movement].queue)
                total = 0.0
                for ref in refs:
                    other = by_id.get(ref["intersection_id"])
                    if other is not None:
                        total += float(other.lanes[ref["lane"]].queue)
                downstream[movement] = total
        else:
            for movement in CONTROLLED_LANES:
                upstream[movement] = float(observation.lanes[movement].queue)
        return upstream, downstream, topology_available

    @staticmethod
    def _choose_phase_index(
        phases: Sequence[str],
        upstream: Dict[str, float],
        downstream: Dict[str, float],
    ) -> int:
        """Verbatim scoring of RLLightMaxPressureHeuristic.choose_action."""
        best_idx = 0
        best_score = -float("inf")
        for phase_idx, phase_name in enumerate(phases):
            score = 0.0
            matched = False
            for movement in phase_lanes(phase_name):
                up = upstream.get(movement, 0.0)
                down = downstream.get(movement, 0.0)
                score += up - down
                matched = matched or bool(up or down)
            if not matched:
                score = 0.0
            if score > best_score:
                best_score = score
                best_idx = phase_idx
        return best_idx

    def decide(
        self,
        observations: Sequence[IntersectionObservation],
        step: int,
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
        by_id = {observation.intersection_id: observation for observation in observations}
        actions: Dict[str, int] = {}
        traces: List[Dict[str, Any]] = []
        for observation in observations:
            upstream, downstream, topology_available = self._upstream_downstream(
                observation, by_id
            )
            scores: Dict[str, float] = {}
            for phase in observation.phases:
                canonical = canonical_phase_name(phase)
                if canonical not in scores:
                    scores[canonical] = sum(
                        upstream.get(movement, 0.0) - downstream.get(movement, 0.0)
                        for movement in phase_lanes(canonical)
                    )
            best_idx = self._choose_phase_index(
                [canonical_phase_name(phase) for phase in observation.phases],
                upstream,
                downstream,
            )
            actions[observation.intersection_id] = best_idx
            traces.append({
                "step": step,
                "intersection": observation.intersection_id,
                "controller": "maxpressure",
                "agent_mode": "maxpressure",
                "packaging": "none",
                "transport": "local",
                "model": "maxpressure",
                "signal": canonical_phase_name(observation.phases[best_idx]),
                "pressures": scores,
                "upstream": upstream,
                "downstream": downstream,
                "topology_available": topology_available,
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
