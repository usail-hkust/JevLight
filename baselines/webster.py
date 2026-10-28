"""Webster baseline: refined Webster cycle-time method as a signal controller.

The ``Webster`` class below implements the refined Webster timing method.
The ``WebsterController`` wraps it for the JevLight controller contract:
every ``update_frequency`` seconds it rebuilds ``lane_conditions`` from the
current observations, recomputes the per-phase green times, and follows the
plan by holding each phase for whole decision intervals.

Lane conditions are built so the class's own math recovers the observed
vehicle count: ``lane_density = count * vehicle_length / road_length`` feeds
``vehicle_count = density * lane_length / VEHICLE_LENGTH``
(``webster.py:122-125``), then ``flow_rate = vehicle_count /
UPDATE_FREQUENCY`` and ``flow_ratio = flow_rate / SATURATION_FLOW`` — a
per-window demand estimate matching the source's intent.  With the default
15 s decision interval and ``min_green_time`` 8 s every phase gets at least
one full interval; the yellow time is charged to each transition
(``lost_time_per_phase`` stays 0 as in the source class).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

from jevlight.observation import (
    CONTROLLED_LANES,
    IntersectionObservation,
    canonical_phase_name,
)


class Webster:
    """
    Refined Webster algorithm implementation based on best practices
    """

    def __init__(self,
                 lost_time_per_phase: float = 0.0,
                 saturation_flow: float = 0.38,  # vehicles/second
                 min_green_time: float = 8.0,
                 min_cycle_time: float = 32.0,
                 max_cycle_time: float = 120.0,
                 vehicle_length: float = 8.0,  # average vehicle length in meters
                 update_frequency: int = 60):  # seconds
        self.LOST_TIME_PER_PHASE = lost_time_per_phase
        self.SATURATION_FLOW = saturation_flow
        self.MIN_GREEN_TIME = min_green_time  # noqa: E221 - verbatim port
        self.MIN_CYCLE_TIME = min_cycle_time
        self.MAX_CYCLE_TIME = max_cycle_time
        self.VEHICLE_LENGTH = vehicle_length
        self.UPDATE_FREQUENCY = update_frequency

    def webster_batch_algorithm(self, last_lane_conditions: Dict[str, Dict[str, Any]],
                              available_phases: dict) -> Dict[str, Any]:
        """Process multiple intersections"""
        all_timing = {}
        for inter in last_lane_conditions:
            all_timing[inter] = self.webster_algorithm(last_lane_conditions[inter], available_phases[inter])
        return all_timing

    def webster_algorithm(self, last_lane_conditions: Dict[str, Dict[str, Any]],
                         available_phases: list) -> Dict[str, Any]:
        """
        Refined Webster algorithm implementation based on standard Webster method
        """
        # Safety check for empty available_phases
        if not available_phases:
            return {
                'duration': {},
                'cycle_length': round(self.MIN_CYCLE_TIME, 2),
                'flow_ratios': {},
                'total_critical_ratio': 0.0
            }

        # Calculate flow ratios based on lane density
        flow_ratios = self._calculate_flow_ratios(last_lane_conditions, available_phases)

        # Find critical flow ratios
        critical_flow_ratios = self._find_critical_flow_ratios(flow_ratios)

        # Calculate total critical flow ratio (Y)
        Y = sum(critical_flow_ratios.values())

        # Calculate total lost time per cycle
        L = len(available_phases) * self.LOST_TIME_PER_PHASE

        # Step 1: Compute optimal cycle length (C)
        optimal_cycle_length = (1.5 * L + 5) / (1 - Y)
        optimal_cycle_length = max(self.MIN_CYCLE_TIME, min(optimal_cycle_length, self.MAX_CYCLE_TIME))

        # Step 2: Compute total effective green time (g = C - L)
        effective_green = optimal_cycle_length - L

        # Step 3: Allocate green time to each phase proportionally
        phase_durations = {}
        if Y > 0:
            for phase in available_phases:
                ratio = critical_flow_ratios.get(phase, 0.0)
                green_time = (ratio / Y) * effective_green
                # Ensure minimum green time
                phase_durations[phase] = round(max(green_time, self.MIN_GREEN_TIME))
        else:
            # Equal distribution if no flow
            green_per_phase = effective_green / len(available_phases)
            for phase in available_phases:
                phase_durations[phase] = round(max(green_per_phase, self.MIN_GREEN_TIME))

        optimal_cycle_length = sum(phase_durations.values())

        return {
            'duration': phase_durations,
            'cycle_length': round(optimal_cycle_length, 2),
            'flow_ratios': {phase: round(ratio, 2) for phase, ratio in critical_flow_ratios.items()},
            'total_critical_ratio': round(Y, 2)
        }

    def _calculate_flow_ratios(self, lane_conditions: Dict[str, Dict[str, Any]],
                             available_phases: List[str]) -> Dict[str, List[float]]:
        """Calculate flow ratios based on lane density"""
        # Map directions to phases
        direction_to_phase = {
            "north-go_straight": "NT",
            "north-turn_left": "NL",
            "south-go_straight": "ST",
            "south-turn_left": "SL",
            "east-go_straight": "ET",
            "east-turn_left": "EL",
            "west-go_straight": "WT",
            "west-turn_left": "WL"
        }

        # Initialize flow ratios for each phase
        flow_ratios = {phase: [] for phase in available_phases}

        # Calculate flow ratio for each lane
        for lane_id, lane_data in lane_conditions.items():
            direction = lane_data.get('direction', '')
            traffic = lane_data.get('traffic', {})
            movement = direction_to_phase.get(direction)

            if not movement:
                continue

            # Calculate vehicle count from density and length
            density = traffic.get('lane_density', 0)
            lane_length = traffic.get('lane_length', 0)

            # Safety check for division by zero
            if self.VEHICLE_LENGTH <= 0:
                vehicle_count = 0
            else:
                vehicle_count = (density * lane_length) / self.VEHICLE_LENGTH

            # Calculate flow rate (vehicles per second)
            if self.UPDATE_FREQUENCY <= 0:
                flow_rate = 0
            else:
                flow_rate = vehicle_count / self.UPDATE_FREQUENCY

            # Calculate flow ratio
            if self.SATURATION_FLOW <= 0:
                flow_ratio = 0
            else:
                flow_ratio = flow_rate / self.SATURATION_FLOW

            # Add flow ratio to all relevant phases
            for phase in available_phases:
                if movement in phase:
                    flow_ratios[phase].append(flow_ratio)

        # Ensure each phase has at least one flow ratio
        for phase in flow_ratios:
            if not flow_ratios[phase]:
                flow_ratios[phase] = [0.0]

        return flow_ratios

    def _constrain_critical_ratio(self, Y: float) -> float:
        """Apply constraints to total critical ratio Y"""
        if Y > 0.85:
            return 0.85
        elif Y <= 0.0:
            return 0.01
        return Y

    def _find_critical_flow_ratios(self, flow_ratios: Dict[str, List[float]]) -> Dict[str, float]:
        """Find the critical (maximum) flow ratio for each phase"""
        critical_ratios = {}
        for phase, ratios in flow_ratios.items():
            if ratios:  # Check if list is not empty
                critical_ratios[phase] = max(ratios)
            else:
                critical_ratios[phase] = 0.0
        return critical_ratios


class WebsterController:
    """Webster timing plans recomputed every update window, then followed."""

    DIRECTION = {"N": "north", "S": "south", "E": "east", "W": "west"}
    MOVEMENT_NAME = {"T": "go_straight", "L": "turn_left"}

    def __init__(
        self,
        phase_duration: float,
        update_frequency: int = 60,
        min_green_time: float = 8.0,
        min_cycle_time: float = 32.0,
        max_cycle_time: float = 120.0,
        saturation_flow: float = 0.38,
        vehicle_length: float = 8.0,
    ):
        self.phase_duration = phase_duration
        self.vehicle_length = vehicle_length
        self.update_frequency = update_frequency
        self.webster = Webster(
            lost_time_per_phase=0.0,
            saturation_flow=saturation_flow,
            min_green_time=min_green_time,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            vehicle_length=vehicle_length,
            update_frequency=update_frequency,
        )
        # Per-intersection plan state:
        #   {"last_plan_step", "hold_steps": [...], "phase_index", "steps_held", "plan"}
        self._plans: Dict[str, Dict[str, Any]] = {}

    def _lane_conditions(
        self, observation: IntersectionObservation
    ) -> Dict[str, Dict[str, Any]]:
        conditions: Dict[str, Dict[str, Any]] = {}
        for movement in CONTROLLED_LANES:
            lane = observation.lanes[movement]
            road_length = float(lane.road_length or 0.0)
            count = len(lane.vehicles)
            conditions[movement] = {
                "direction": (
                    f"{self.DIRECTION[movement[0]]}-{self.MOVEMENT_NAME[movement[1]]}"
                ),
                "traffic": {
                    "lane_density": (
                        count * self.vehicle_length / road_length
                        if road_length > 0
                        else 0.0
                    ),
                    "lane_length": road_length,
                },
            }
        return conditions

    def _build_plan(self, observation: IntersectionObservation) -> Dict[str, Any]:
        available_phases = [
            canonical_phase_name(phase) for phase in observation.phases
        ]
        plan = self.webster.webster_algorithm(
            self._lane_conditions(observation), available_phases
        )
        durations = plan["duration"]
        hold_steps = []
        for phase in available_phases:
            green = float(durations.get(phase, 0.0))
            hold_steps.append(max(1, math.ceil(green / self.phase_duration)))
        return {"plan": plan, "hold_steps": hold_steps, "available_phases": available_phases}

    def decide(
        self,
        observations: Sequence[IntersectionObservation],
        step: int,
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
        actions: Dict[str, int] = {}
        traces: List[Dict[str, Any]] = []
        for observation in observations:
            if not observation.phases:
                actions[observation.intersection_id] = 0
                continue
            state = self._plans.get(observation.intersection_id)
            replanned = False
            elapsed_since_plan = (
                (step - state["last_plan_step"]) * self.phase_duration
                if state is not None
                else float("inf")
            )
            if state is None or elapsed_since_plan >= self.update_frequency:
                built = self._build_plan(observation)
                if state is None:
                    state = {
                        "last_plan_step": step,
                        "phase_index": 0,
                        "steps_held": 0,
                        **built,
                    }
                else:
                    state.update(
                        {"last_plan_step": step, **built}
                    )
                    # Keep the cursor; hold steps refresh from the new plan.
                self._plans[observation.intersection_id] = state
                replanned = True
            hold = state["hold_steps"][state["phase_index"]]
            if state["steps_held"] >= hold:
                state["phase_index"] = (state["phase_index"] + 1) % len(
                    state["available_phases"]
                )
                state["steps_held"] = 0
            state["steps_held"] += 1
            phase_index = state["phase_index"]
            actions[observation.intersection_id] = phase_index
            plan = state["plan"]
            traces.append({
                "step": step,
                "intersection": observation.intersection_id,
                "controller": "webster",
                "agent_mode": "webster",
                "packaging": "none",
                "transport": "local",
                "model": "webster",
                "signal": state["available_phases"][phase_index],
                "phase_index": phase_index,
                "hold_steps": state["hold_steps"][phase_index],
                "steps_held": state["steps_held"],
                "cycle_length": plan["cycle_length"],
                "durations": plan["duration"],
                "flow_ratios": plan["flow_ratios"],
                "total_critical_ratio": plan["total_critical_ratio"],
                "replanned": replanned,
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
