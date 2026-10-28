"""FixedTime baseline controller unit tests (no network, no SUMO)."""

from __future__ import annotations

import pytest

from baselines.fixedtime import FixedTimeController, DEFAULT_SPLIT_SECONDS
from jevlight.observation import IntersectionObservation, LaneObservation


PHASES = ["WT_ET", "NT_ST", "WL_EL", "NL_SL"]
EIGHT_PHASES = [
    "WT_ET", "WL_EL", "NT_ST", "NL_SL",
    "ST_ET", "SL_EL", "WT_ST", "WL_SL",
]


def make_observation(intersection_id="i0", phases=PHASES, current_phase="WT_ET"):
    lanes = {lane: LaneObservation() for lane in (
        "NT", "NL", "NR", "ST", "SL", "SR",
        "ET", "EL", "ER", "WT", "WL", "WR",
    )}
    return IntersectionObservation(
        intersection_id=intersection_id,
        lanes=lanes,
        phases=list(phases),
        neighbours=[],
        empty=False,
        current_phase=current_phase,
    )


def signals(controller, steps, phases=PHASES):
    observation = make_observation(phases=phases)
    picked = []
    for step in range(steps):
        actions, traces = controller.decide([observation], step)
        picked.append(actions["i0"])
    return picked


class TestFixedTimeController:
    def test_uniform_splits_rotate_every_step(self):
        controller = FixedTimeController(15, splits="15,15,15,15")
        assert signals(controller, 8) == [0, 1, 2, 3, 0, 1, 2, 3]

    def test_longer_split_holds_extra_step(self):
        controller = FixedTimeController(15, splits="30,15,15,15")
        assert signals(controller, 8) == [0, 0, 1, 2, 3, 0, 0, 1]

    def test_non_divisor_split_rounds_up(self):
        controller = FixedTimeController(15, splits="20,15,15,15")
        assert signals(controller, 6) == [0, 0, 1, 2, 3, 0]

    def test_split_shorter_than_interval_still_gets_one_step(self):
        controller = FixedTimeController(15, splits="8,15,15,15")
        assert signals(controller, 5) == [0, 1, 2, 3, 0]

    def test_default_splits_are_the_source_uniform_plan(self):
        assert FixedTimeController(15).splits == [15, 15, 15, 15]
        assert DEFAULT_SPLIT_SECONDS == 15

    def test_eight_phase_rotation(self):
        controller = FixedTimeController(15, splits="15,15,15,15,15,15,15,15")
        assert signals(controller, 9, phases=EIGHT_PHASES) == [
            0, 1, 2, 3, 4, 5, 6, 7, 0,
        ]

    def test_phase_count_mismatch_falls_back_to_uniform_plan(self):
        controller = FixedTimeController(15, splits="15,15,15,15")
        observation = make_observation(phases=EIGHT_PHASES[:3])
        actions, traces = controller.decide([observation], 0)
        assert actions["i0"] == 0
        assert traces[0]["splits"] == [DEFAULT_SPLIT_SECONDS] * 3

    def test_starts_from_current_phase(self):
        controller = FixedTimeController(15, splits="15,15,15,15")
        observation = make_observation(current_phase="WL_EL")
        actions, _ = controller.decide([observation], 0)
        assert actions["i0"] == 2

    def test_trace_fields(self):
        controller = FixedTimeController(15, splits="30,15,15,15")
        observation = make_observation()
        _, traces = controller.decide([observation], 0)
        trace = traces[0]
        assert trace["controller"] == "fixedtime"
        assert trace["signal"] == "ETWT"
        assert trace["phase_index"] == 0
        assert trace["split_s"] == 30
        assert trace["hold_steps"] == 2
        assert trace["steps_held"] == 1
        assert trace["fallback"] is None

    def test_usage_summary_is_local(self):
        summary = FixedTimeController(15).usage_summary()
        assert summary == {
            "requests": 0,
            "failures": 0,
            "rate_limited": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_mean_s": None,
            "latency_max_s": None,
        }

    def test_invalid_splits_rejected(self):
        with pytest.raises(ValueError):
            FixedTimeController(15, splits="15,0,15,15")
        with pytest.raises(ValueError):
            FixedTimeController(15, splits="15,x,15,15")
        with pytest.raises(ValueError):
            FixedTimeController(15, splits="")

    def test_empty_phases_act_safely(self):
        controller = FixedTimeController(15)
        observation = make_observation(phases=[])
        actions, traces = controller.decide([observation], 0)
        assert actions["i0"] == 0
        assert traces == []
