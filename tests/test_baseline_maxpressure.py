"""Strict-lane-pressure MaxPressure baseline unit tests (no network, no SUMO)."""

from __future__ import annotations

from baselines.maxpressure import StrictLaneMaxPressureController
from jevlight.observation import IntersectionObservation, LaneObservation


PHASES = ["WT_ET", "NT_ST", "WL_EL", "NL_SL"]
ALL_LANES = (
    "NT", "NL", "NR", "ST", "SL", "SR",
    "ET", "EL", "ER", "WT", "WL", "WR",
)


def make_observation(
    intersection_id="A",
    queues=None,
    phases=PHASES,
    lane_relations=None,
    topology_available=True,
    current_phase="WT_ET",
):
    lanes = {lane: LaneObservation() for lane in ALL_LANES}
    for movement, queue in (queues or {}).items():
        lanes[movement].queue = float(queue)
    observation = IntersectionObservation(
        intersection_id=intersection_id,
        lanes=lanes,
        phases=list(phases),
        neighbours=[],
        empty=False,
        current_phase=current_phase,
        lane_relations=lane_relations or {},
        topology_available=topology_available,
    )
    return observation


def downstream_relations(mapping):
    return {
        movement: {"upstream": [], "downstream": list(refs)}
        for movement, refs in mapping.items()
    }


class TestStrictLaneMaxPressureController:
    def test_score_is_upstream_minus_downstream(self):
        # A's ET/WT feed B's WT/ET; every other movement exits the network
        # (no downstream junction => no contribution, as in the source graph).
        controller = StrictLaneMaxPressureController(15)
        a = make_observation(
            "A",
            queues={"ET": 5, "WT": 2, "NT": 1, "EL": 4},
            lane_relations=downstream_relations({
                "ET": [{"intersection_id": "B", "lane": "WT"}],
                "WT": [{"intersection_id": "B", "lane": "ET"}],
                "NT": [], "ST": [], "EL": [], "WL": [], "NL": [], "SL": [],
            }),
        )
        b = make_observation(
            "B",
            queues={"WT": 3, "ET": 1},
            lane_relations=downstream_relations({
                "WT": [{"intersection_id": "A", "lane": "ET"}],
                "ET": [{"intersection_id": "A", "lane": "WT"}],
                "NT": [], "ST": [], "EL": [], "WL": [], "NL": [], "SL": [],
            }),
        )
        actions, traces = controller.decide([a, b], 0)
        # ETWT: (5-3) + (2-1) = 3; all other phases have no graph movements => 0.
        assert actions["A"] == 0
        trace = traces[0]
        assert trace["pressures"]["ETWT"] == 3.0
        assert trace["pressures"] == {"ETWT": 3.0, "NTST": 0.0, "ELWL": 0.0, "NLSL": 0.0}
        assert trace["upstream"] == {"ET": 5.0, "WT": 2.0}
        assert trace["downstream"] == {"ET": 3.0, "WT": 1.0}
        assert trace["topology_available"] is True
        assert trace["signal"] == "ETWT"

    def test_boundary_movements_do_not_contribute(self):
        # NT has a queue but exits the network: NTST must score 0, not 1.
        controller = StrictLaneMaxPressureController(15)
        a = make_observation(
            "A",
            queues={"NT": 1},
            lane_relations=downstream_relations({
                "ET": [{"intersection_id": "B", "lane": "WT"}],
                "NT": [], "ST": [], "WT": [], "EL": [], "WL": [], "NL": [], "SL": [],
            }),
        )
        b = make_observation("B")
        _, traces = controller.decide([a, b], 0)
        assert traces[0]["pressures"]["NTST"] == 0.0
        assert "NT" not in traces[0]["upstream"]

    def test_no_topology_degrades_to_upstream_only(self):
        controller = StrictLaneMaxPressureController(15)
        a = make_observation(
            "A",
            queues={"NT": 3, "ST": 2, "ET": 1},
            lane_relations={},
            topology_available=False,
        )
        actions, traces = controller.decide([a], 0)
        # NTST: (3-0)+(2-0)=5 beats ETWT: 1 and the empty phases.
        assert actions["A"] == 1
        assert traces[0]["upstream"] == {
            "NT": 3.0, "NL": 0.0, "ST": 2.0, "SL": 0.0,
            "ET": 1.0, "EL": 0.0, "WT": 0.0, "WL": 0.0,
        }
        assert traces[0]["downstream"] == {}
        assert traces[0]["topology_available"] is False

    def test_tie_keeps_earlier_phase(self):
        controller = StrictLaneMaxPressureController(15)
        a = make_observation("A")  # all queues zero: every phase scores 0
        actions, _ = controller.decide([a], 0)
        assert actions["A"] == 0

    def test_missing_downstream_intersection_counts_zero(self):
        # The lane_relations reference points at an absent intersection id.
        controller = StrictLaneMaxPressureController(15)
        a = make_observation(
            "A",
            queues={"ET": 4},
            lane_relations=downstream_relations({
                "ET": [{"intersection_id": "GHOST", "lane": "WT"}],
                "WT": [], "NT": [], "ST": [], "EL": [], "WL": [], "NL": [], "SL": [],
            }),
        )
        actions, traces = controller.decide([a], 0)
        assert actions["A"] == 0
        assert traces[0]["downstream"] == {"ET": 0.0}

    def test_downstream_sum_aggregates_multiple_destinations(self):
        controller = StrictLaneMaxPressureController(15)
        a = make_observation(
            "A",
            queues={"ET": 6, "NT": 2},
            lane_relations=downstream_relations({
                "ET": [
                    {"intersection_id": "B", "lane": "WT"},
                    {"intersection_id": "C", "lane": "WT"},
                ],
                "WT": [], "NT": [], "ST": [], "EL": [], "WL": [], "NL": [], "SL": [],
            }),
        )
        b = make_observation("B", queues={"WT": 2})
        c = make_observation("C", queues={"WT": 3})
        actions, traces = controller.decide([a, b, c], 0)
        # ETWT: (6 - (2+3)) + (0-0) = 1; NTST has no graph movement => 0.
        assert actions["A"] == 0
        assert traces[0]["pressures"]["ETWT"] == 1.0

    def test_usage_summary_is_local(self):
        summary = StrictLaneMaxPressureController(15).usage_summary()
        assert summary["requests"] == 0
        assert summary["latency_mean_s"] is None
