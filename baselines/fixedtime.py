"""FixedTime baseline: uniform green splits rotated on the decision cadence.

The classic FixedTime plan is one green split per phase in cycle order, 15 s
each by default.  On JevLight's decision cadence the controller holds each
phase for ``ceil(split / decision_interval)`` decision steps, then advances
to the next phase in the intersection's own ``phases`` order.  Re-sending the
same action index holds the green; a changed index triggers the 5 s yellow
(``Intersection.set_signal``).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple, Union

from jevlight.observation import (
    IntersectionObservation,
    canonical_phase_name,
)

# The uniform plan: 15 s per phase regardless of the phase count.
DEFAULT_SPLIT_SECONDS = 15


class FixedTimeController:
    """FixedTime plan follower exposing the JevLight controller contract."""

    def __init__(
        self,
        phase_duration: float,
        splits: Union[None, str, Sequence[int]] = None,
    ):
        self.phase_duration = phase_duration
        self.splits = self._parse_splits(splits)
        # Per-intersection cursor: [phase index into observation.phases, steps held].
        self._cursor: Dict[str, List[int]] = {}
        # Intersections whose phase count did not match the configured splits.
        self._uniform_fallbacks: List[str] = []

    @staticmethod
    def _parse_splits(splits: Union[None, str, Sequence[int]]) -> List[int]:
        if splits is None:
            return [DEFAULT_SPLIT_SECONDS] * 4
        if isinstance(splits, str):
            parts = [part.strip() for part in splits.split(",") if part.strip()]
            if not parts:
                raise ValueError("fixed_time_splits must contain at least one value")
            try:
                values = [int(part) for part in parts]
            except ValueError as exc:
                raise ValueError(
                    f"fixed_time_splits must be integers: {splits!r}"
                ) from exc
        else:
            values = [int(split) for split in splits]
        if not values or any(value <= 0 for value in values):
            raise ValueError("fixed_time_splits must be positive integers")
        return values

    def _hold_steps(self, split_seconds: int) -> int:
        return max(1, math.ceil(split_seconds / self.phase_duration))

    def _splits_for(self, observation: IntersectionObservation) -> List[int]:
        """Configured splits when the phase count matches, else the uniform plan."""
        if len(self.splits) == len(observation.phases):
            return self.splits
        if observation.intersection_id not in self._uniform_fallbacks:
            self._uniform_fallbacks.append(observation.intersection_id)
            print(
                f"[fixedtime] {observation.intersection_id} has "
                f"{len(observation.phases)} phases but {len(self.splits)} splits "
                f"were configured; using the uniform {DEFAULT_SPLIT_SECONDS}s plan",
                flush=True,
            )
        return [DEFAULT_SPLIT_SECONDS] * len(observation.phases)

    def _initial_phase_index(self, observation: IntersectionObservation) -> int:
        if observation.current_phase is not None:
            for index, available in enumerate(observation.phases):
                if canonical_phase_name(available) == canonical_phase_name(
                    observation.current_phase
                ):
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
            if not observation.phases:
                actions[observation.intersection_id] = 0
                continue
            splits = self._splits_for(observation)
            cursor = self._cursor.get(observation.intersection_id)
            if cursor is None:
                cursor = [self._initial_phase_index(observation), 0]
            phase_index, steps_held = cursor
            if steps_held >= self._hold_steps(splits[phase_index]):
                phase_index = (phase_index + 1) % len(observation.phases)
                steps_held = 0
            steps_held += 1
            self._cursor[observation.intersection_id] = [phase_index, steps_held]
            actions[observation.intersection_id] = phase_index
            traces.append({
                "step": step,
                "intersection": observation.intersection_id,
                "controller": "fixedtime",
                "agent_mode": "fixedtime",
                "packaging": "none",
                "transport": "local",
                "model": "fixedtime",
                "signal": canonical_phase_name(observation.phases[phase_index]),
                "phase_index": phase_index,
                "split_s": splits[phase_index],
                "hold_steps": self._hold_steps(splits[phase_index]),
                "steps_held": steps_held,
                "splits": splits,
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
