"""Webster baseline controller unit tests (no network, no SUMO)."""

from __future__ import annotations

import math

from baselines.webster import Webster, WebsterController
from jevlight.observation import IntersectionObservation, LaneObservation


PHASES = ["WT_ET", "NT_ST", "WL_EL", "NL_SL"]


def make_lane(queue=0.0, vehicles=0, road_length=100.0):
    lane = LaneObservation()
    lane.queue = float(queue)
    lane.road_length = float(road_length)
    lane.vehicles = {f"v{i}": 0 for i in range(vehicles)}
    return lane


def make_observation(intersection_id="i0", vehicle_counts=None, road_length=100.0):
    lanes = {lane: make_lane(road_length=road_length) for lane in (
        "NT", "NL", "NR", "ST", "SL", "SR",
        "ET", "EL", "ER", "WT", "WL", "WR",
    )}
    for movement, count in (vehicle_counts or {}).items():
        lanes[movement].vehicles = {f"{movement}{i}": 0 for i in range(count)}
    return IntersectionObservation(
        intersection_id=intersection_id,
        lanes=lanes,
        phases=list(PHASES),
        neighbours=[],
        empty=False,
        current_phase="WT_ET",
    )


class TestWebsterClass:
    def test_symmetric_demand_splits_cycle_equally(self):
        webster = Webster()
        conditions = {
            movement: {
                "direction": f"{direction}-{movement_name}",
                "traffic": {"lane_density": 5 * 8 / 100, "lane_length": 100},
            }
            for movement, direction, movement_name in [
                ("ET", "east", "go_straight"), ("WT", "west", "go_straight"),
                ("NT", "north", "go_straight"), ("ST", "south", "go_straight"),
                ("EL", "east", "turn_left"), ("WL", "west", "turn_left"),
                ("NL", "north", "turn_left"), ("SL", "south", "turn_left"),
            ]
        }
        result = webster.webster_algorithm(conditions, ["ETWT", "NTST", "ELWL", "NLSL"])
        # 5 vehicles per movement: ratio = (5/60)/0.38 = 0.2193 per lane, each
        # phase's critical ratio is the same, Y = 0.877 and C = 5/(1-Y) = 40.7
        # (inside [32,120]); the equal split gives every phase round(40.7/4)=10 s.
        assert result["cycle_length"] == 40
        assert result["duration"] == {"ETWT": 10, "NTST": 10, "ELWL": 10, "NLSL": 10}
        assert all(seconds >= 8 for seconds in result["duration"].values())
        assert sum(result["duration"].values()) == result["cycle_length"]

    def test_no_flow_splits_equally(self):
        webster = Webster()
        result = webster.webster_algorithm({}, ["ETWT", "NTST", "ELWL", "NLSL"])
        assert result["total_critical_ratio"] == 0.0
        assert result["duration"] == {"ETWT": 8, "NTST": 8, "ELWL": 8, "NLSL": 8}
        assert result["cycle_length"] == 32


class TestWebsterController:
    def test_lane_conditions_recover_vehicle_counts(self):
        controller = WebsterController(15)
        observation = make_observation(vehicle_counts={"ET": 5, "NL": 2})
        conditions = controller._lane_conditions(observation)
        assert conditions["ET"]["direction"] == "east-go_straight"
        assert conditions["NL"]["direction"] == "north-turn_left"
        assert conditions["ET"]["traffic"]["lane_length"] == 100.0
        # The class's own math must recover the observed count:
        # vehicle_count = density * lane_length / VEHICLE_LENGTH.
        assert conditions["ET"]["traffic"]["lane_density"] == 5 * 8 / 100
        recovered = (
            conditions["ET"]["traffic"]["lane_density"]
            * conditions["ET"]["traffic"]["lane_length"]
            / controller.webster.VEHICLE_LENGTH
        )
        assert math.isclose(recovered, 5.0)

    def test_plan_math_on_asymmetric_demand(self):
        controller = WebsterController(15)
        observation = make_observation(vehicle_counts={"ET": 5})
        actions, traces = controller.decide([observation], 0)
        trace = traces[0]
        # ET: 5 vehicles / 100 m -> ratio = (5/60)/0.38 = 0.2193; Y = 0.2193;
        # C = 5/(1-Y) = 6.4 -> clamped to 32; ETWT green = 32, others floored
        # to the 8 s minimum; cycle = 32 + 3*8 = 56.
        assert trace["cycle_length"] == 56
        assert trace["durations"] == {"ETWT": 32, "NTST": 8, "ELWL": 8, "NLSL": 8}
        assert trace["flow_ratios"]["ETWT"] == 0.22
        assert trace["hold_steps"] == 3  # ceil(32/15)
        assert trace["phase_index"] == 0
        assert trace["replanned"] is True
        assert trace["signal"] == "ETWT"
        assert actions["i0"] == 0

    def test_plan_followed_between_recomputes(self):
        controller = WebsterController(15, update_frequency=60)
        observation = make_observation(vehicle_counts={"ET": 5})
        seen = []
        for step in range(6):
            actions, traces = controller.decide([observation], step)
            seen.append((actions["i0"], traces[0]["replanned"], traces[0]["phase_index"]))
        # hold_steps [3,1,1,1]: phase 0 for steps 0-2, then 1, 2; the plan is
        # recomputed at step 4 ((4-0)*15 >= 60) without resetting the cursor.
        assert seen == [
            (0, True, 0),
            (0, False, 0),
            (0, False, 0),
            (1, False, 1),
            (2, True, 2),
            (3, False, 3),
        ]

    def test_empty_demand_yields_equal_split_cycle(self):
        controller = WebsterController(15)
        observation = make_observation()
        _, traces = controller.decide([observation], 0)
        assert traces[0]["durations"] == {"ETWT": 8, "NTST": 8, "ELWL": 8, "NLSL": 8}
        assert traces[0]["cycle_length"] == 32

    def test_empty_phases_act_safely(self):
        controller = WebsterController(15)
        observation = make_observation()
        observation.phases = []
        actions, traces = controller.decide([observation], 0)
        assert actions["i0"] == 0
        assert traces == []

    def test_usage_summary_is_local(self):
        summary = WebsterController(15).usage_summary()
        assert summary["requests"] == 0
        assert summary["latency_max_s"] is None
