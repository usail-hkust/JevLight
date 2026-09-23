"""Unit tests for the JevLight controller and client (no network, no SUMO)."""

from __future__ import annotations

from typing import Any, List, Mapping

import pytest

from jevlight.controller import (
    CONGESTION_QUESTION_PREFIX,
    JevLightController,
    PHASE_QUESTION_PREFIX,
    congestion_question,
    jev_intersection_state,
    phase_criteria,
    phase_question,
)
from jevlight.jev_client import (
    JevClient,
    JevResult,
    resolve_jev_api_key,
)
from jevlight.observation import (
    CANONICAL_PHASES,
    IntersectionObservation,
    LaneObservation,
    rank_phases,
)


PHASES = ["WT_ET", "NT_ST", "WL_EL", "NL_SL"]


def make_lane(queue=0, cells=(0, 0, 0, 0), waiting=0.0, occupancy=0.0):
    lane = LaneObservation()
    lane.queue = float(queue)
    # rank_phases reads the ten uniform queued/moving cells, not the scalar
    # queue; queued vehicles sit in segment 0 (nearest the junction).
    lane.queue_cells[0] = float(queue)
    lane.llmlight_cells = list(cells)
    lane.avg_wait = float(waiting)
    lane.occupancy = float(occupancy)
    return lane


def make_observation(
    intersection_id="i0",
    queue_by_phase=None,
    waiting=0.0,
    phases=PHASES,
    empty=False,
    current_phase="WT_ET",
):
    lanes = {lane: make_lane() for lane in (
        "NT", "NL", "NR", "ST", "SL", "SR",
        "ET", "EL", "ER", "WT", "WL", "WR",
    )}
    for phase, queue in (queue_by_phase or {}).items():
        for lane_name in (phase[:2], phase[2:]):
            lanes[lane_name].queue = float(queue)
            lanes[lane_name].queue_cells[0] = float(queue)
    for lane in lanes.values():
        lane.avg_wait = waiting
    return IntersectionObservation(
        intersection_id=intersection_id,
        lanes=lanes,
        phases=list(phases),
        neighbours=[],
        empty=empty,
        current_phase=current_phase,
    )


class StubJevClient(JevClient):
    """Captures requests and replays scripted results."""

    def __init__(self, results: List[JevResult] = None):
        super().__init__(mock=True)
        self.results = list(results or [])
        self.requests: List[Mapping[str, Any]] = []

    def evaluate(self, state, questions):
        self.requests.append({"state": state, "questions": dict(questions)})
        if self.results:
            return self.results.pop(0)
        return JevResult()


def phase_answer(signal, confidence=0.9, probabilities=None):
    return {
        "type": "choice",
        "choice": signal,
        "probabilities": probabilities
        or {name: 0.25 for name in CANONICAL_PHASES},
        "confidence": confidence,
    }


class TestStateAndQuestions:
    def test_intersection_state_shape(self):
        observation = make_observation(queue_by_phase={"ETWT": 4}, waiting=12.0)
        state = jev_intersection_state(observation, 15)
        assert state["intersection_id"] == "i0"
        assert state["phase_duration_s"] == 15
        assert state["current_phase"] == "ETWT"
        assert set(state["lanes"]) == {
            "NT", "NL", "ST", "SL", "ET", "EL", "WT", "WL",
        }
        assert state["lanes"]["ET"]["queue"] == 4
        assert state["lanes"]["WT"]["queue"] == 4
        assert state["lanes"]["ET"]["average_waiting_time_s"] == 12.0
        assert state["lanes"]["ET"]["approaching_by_segment"] == [0, 0, 0]

    def test_segment_merging_matches_llmlight_cells(self):
        observation = make_observation()
        observation.lanes["NT"].llmlight_cells = [1, 2, 3, 4]
        state = jev_intersection_state(observation, 15)
        assert state["lanes"]["NT"]["approaching_by_segment"] == [1, 2, 7]

    def test_phase_criteria_are_canonical_and_described(self):
        observation = make_observation(phases=PHASES)
        criteria = phase_criteria(observation)
        assert set(criteria) == set(CANONICAL_PHASES)
        for description in criteria.values():
            assert "Activates" in description and "releases" in description

    def test_phase_question_wire_format(self):
        observation = make_observation()
        question = phase_question(observation, 30, "intersections.i0")
        assert question["type"] == "choice"
        assert "intersections.i0" in question["instructions"]
        assert set(question["criteria"]) == set(CANONICAL_PHASES)

    def test_congestion_question_is_noul(self):
        question = congestion_question("intersections.i0")
        assert question["type"] == "noul"
        assert "intersections.i0" in question["instructions"]


class TestNetworkPackaging:
    def test_one_request_with_all_active_questions(self):
        observations = [
            make_observation("i0", queue_by_phase={"ETWT": 3}),
            make_observation("i1", queue_by_phase={"NTST": 5}, empty=True),
        ]
        client = StubJevClient(
            results=[
                JevResult(
                    answers={
                        f"{PHASE_QUESTION_PREFIX}i0": phase_answer("ETWT"),
                        f"{CONGESTION_QUESTION_PREFIX}i0": {
                            "type": "noul",
                            "noul": 0.4,
                        },
                    },
                    input_tokens=500,
                    output_tokens=10,
                )
            ]
        )
        controller = JevLightController(client, 15, packaging="network")
        actions, traces = controller.decide(observations, step=0)

        assert len(client.requests) == 1
        request = client.requests[0]
        # The shared state carries every intersection, empty or not.
        assert set(request["state"]["intersections"]) == {"i0", "i1"}
        # Questions exist only for the active intersection.
        assert set(request["questions"]) == {
            f"{PHASE_QUESTION_PREFIX}i0",
            f"{CONGESTION_QUESTION_PREFIX}i0",
        }
        # The chosen phase maps back onto the SUMO phase list index.
        assert actions == {"i0": 0, "i1": PHASES.index("NT_ST")}
        trace = next(t for t in traces if t["intersection"] == "i0")
        assert trace["signal"] == "ETWT"
        assert trace["confidence"] == 0.9
        assert trace["congestion_noul"] == 0.4
        assert trace["fallback"] is None
        empty_trace = next(t for t in traces if t["intersection"] == "i1")
        assert empty_trace["fallback"] == "empty_junction_local_ranking"
        assert controller.total_requests == 1
        assert controller.total_input_tokens == 500

    def test_empty_junction_uses_exact_local_ranking(self):
        observation = make_observation(
            "i0", queue_by_phase={"NLSL": 7}, empty=True
        )
        controller = JevLightController(StubJevClient(), 15)
        actions, _ = controller.decide([observation], step=0)
        expected = rank_phases(observation, 15)[0][0]
        assert actions["i0"] == PHASES.index("NL_SL")
        assert expected == "NLSL"

    def test_speculative_disabled_drops_noul(self):
        observation = make_observation("i0", queue_by_phase={"ETWT": 1})
        client = StubJevClient(
            results=[
                JevResult(
                    answers={f"{PHASE_QUESTION_PREFIX}i0": phase_answer("ETWT")}
                )
            ]
        )
        controller = JevLightController(
            client, 15, speculative=False
        )
        controller.decide([observation], step=0)
        assert set(client.requests[0]["questions"]) == {
            f"{PHASE_QUESTION_PREFIX}i0"
        }


class TestAnswerGating:
    def base_controller(self, client, **kwargs):
        return JevLightController(client, 15, **kwargs)

    def test_request_error_keeps_previous_signal(self):
        observation = make_observation("i0", queue_by_phase={"ETWT": 2})
        client = StubJevClient(results=[JevResult(error="boom")])
        controller = self.base_controller(client, fallback="previous")
        controller.previous_signals["i0"] = "NLSL"
        actions, traces = controller.decide([observation], step=1)
        assert actions["i0"] == PHASES.index("NL_SL")
        trace = traces[0]
        assert trace["fallback"] == "missing_answer"
        assert trace["signal"] == "NLSL"
        assert controller.total_failures == 1

    def test_rate_limited_result_counts_and_falls_back(self):
        observation = make_observation("i0", queue_by_phase={"ETWT": 2})
        client = StubJevClient(
            results=[
                JevResult(
                    error="jev_decide error: Too many requests.",
                    rate_limited=True,
                )
            ]
        )
        controller = self.base_controller(client)
        controller.previous_signals["i0"] = "NTST"
        actions, traces = controller.decide([observation], step=0)
        assert actions["i0"] == PHASES.index("NT_ST")
        assert traces[0]["fallback"] == "missing_answer"
        assert traces[0]["rate_limited"] is True
        assert controller.total_rate_limited == 1

    def test_invalid_choice_falls_back(self):
        observation = make_observation("i0")
        client = StubJevClient(
            results=[
                JevResult(
                    answers={
                        f"{PHASE_QUESTION_PREFIX}i0": phase_answer("ZZZZ")
                    }
                )
            ]
        )
        controller = self.base_controller(client)
        controller.previous_signals["i0"] = "NTST"
        actions, traces = controller.decide([observation], step=0)
        assert actions["i0"] == PHASES.index("NT_ST")
        assert traces[0]["fallback"] == "invalid_choice"

    def test_low_confidence_falls_back_to_ranking(self):
        observation = make_observation("i0", queue_by_phase={"ELWL": 6})
        client = StubJevClient(
            results=[
                JevResult(
                    answers={
                        f"{PHASE_QUESTION_PREFIX}i0": phase_answer(
                            "ETWT", confidence=0.35
                        )
                    }
                )
            ]
        )
        controller = self.base_controller(
            client, min_confidence=0.6, fallback="ranking"
        )
        actions, traces = controller.decide([observation], step=0)
        # The valid but unconfident ETWT answer is rejected; the local
        # ranking prefers the ELWL pressure.
        assert actions["i0"] == PHASES.index("WL_EL")
        assert traces[0]["fallback"] == "low_confidence"
        assert traces[0]["confidence"] == 0.35

    def test_confident_answer_within_threshold_is_used(self):
        observation = make_observation("i0", queue_by_phase={"ELWL": 6})
        client = StubJevClient(
            results=[
                JevResult(
                    answers={
                        f"{PHASE_QUESTION_PREFIX}i0": phase_answer(
                            "ETWT", confidence=0.61
                        )
                    }
                )
            ]
        )
        controller = self.base_controller(client, min_confidence=0.6)
        actions, traces = controller.decide([observation], step=0)
        assert actions["i0"] == PHASES.index("WT_ET")
        assert traces[0]["fallback"] is None


class TestPerIntersectionPackaging:
    def test_one_request_per_active_intersection(self):
        observations = [
            make_observation("i0", queue_by_phase={"ETWT": 2}),
            make_observation("i1", queue_by_phase={"NTST": 3}),
        ]
        client = StubJevClient(
            results=[
                JevResult(answers={f"{PHASE_QUESTION_PREFIX}i0": phase_answer("ETWT")}),
                JevResult(answers={f"{PHASE_QUESTION_PREFIX}i1": phase_answer("NTST")}),
            ]
        )
        controller = JevLightController(
            client, 15, packaging="per_intersection"
        )
        actions, traces = controller.decide(observations, step=0)
        assert len(client.requests) == 2
        per_request_ids = [
            set(request["questions"]) for request in client.requests
        ]
        assert per_request_ids == [
            {f"{PHASE_QUESTION_PREFIX}i0", f"{CONGESTION_QUESTION_PREFIX}i0"},
            {f"{PHASE_QUESTION_PREFIX}i1", f"{CONGESTION_QUESTION_PREFIX}i1"},
        ]
        for request in client.requests:
            state = request["state"]
            assert "intersections" not in state
            assert "lanes" in state
        assert actions == {"i0": 0, "i1": 1}
        assert len(traces) == 2
        assert controller.total_requests == 2


class TestMockTransport:
    def test_mock_uses_state_pressure(self):
        client = JevClient(mock=True)
        state = {
            "intersections": {
                "i0": {
                    "lanes": {
                        "NT": {"queue": 9, "approaching_by_segment": [0, 0, 0],
                               "average_waiting_time_s": 0, "occupancy": 0},
                        "ST": {"queue": 9, "approaching_by_segment": [0, 0, 0],
                               "average_waiting_time_s": 0, "occupancy": 0},
                    }
                }
            }
        }
        questions = {f"{PHASE_QUESTION_PREFIX}i0": phase_question(
            make_observation(), 15, "intersections.i0"
        )}
        result = client.evaluate(state, questions)
        answer = result.answers[f"{PHASE_QUESTION_PREFIX}i0"]
        assert answer["choice"] == "NTST"
        assert answer["probabilities"]["NTST"] == 0.25


class TestMcpParsing:
    """Parsing logic for the community jev_decide tool payload."""

    @staticmethod
    def decide_result(text: str, is_error: bool = False) -> dict:
        return {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        }

    def make_client(self):
        return JevClient(
            transport="mcp", api_key="jev_test", mock=False
        )

    def test_official_shape_payload(self):
        client = self.make_client()
        payload = (
            '{"model": "jev-1.13.0", "answers": {"phase": '
            '{"type": "choice", "choice": "ETWT", '
            '"probabilities": {"ETWT": 0.8}, "confidence": 0.7}}, '
            '"usage": {"input_tokens": 42, "output_tokens": 8}}'
        )
        result = client._parse_decide_result(
            self.decide_result(payload), started=0.0
        )
        assert result.model == "jev-1.13.0"
        assert result.input_tokens == 42
        assert result.answers["phase"]["choice"] == "ETWT"
        assert result.error is None

    def test_bare_answers_payload(self):
        client = self.make_client()
        payload = (
            '{"phase": {"type": "choice", "choice": "NLSL", '
            '"confidence": 0.66}, "congested": {"type": "noul", "noul": 0.9}}'
        )
        result = client._parse_decide_result(
            self.decide_result(payload), started=0.0
        )
        assert result.answers["phase"]["choice"] == "NLSL"
        assert result.answers["congested"]["noul"] == 0.9

    def test_unparsable_payload_reports_error(self):
        client = self.make_client()
        result = client._parse_decide_result(
            self.decide_result("not json"), started=0.0
        )
        assert result.error.startswith("unparsable jev_decide content")

    def test_rate_limit_marker_detection(self):
        assert JevClient._is_rate_limited("Too many requests. Please try again later.")
        assert JevClient._is_rate_limited("HTTP 429: rate limit exceeded")
        assert not JevClient._is_rate_limited("jev_decide error: bad state")


class TestApiKeyResolution:
    def test_explicit_wins(self, monkeypatch):
        monkeypatch.setenv("JEV_API_KEY", "env-key")
        assert resolve_jev_api_key("explicit-key") == "explicit-key"

    def test_env_order(self, monkeypatch):
        monkeypatch.setenv("JEV_API_KEY", "community-key")
        assert resolve_jev_api_key() == "community-key"
        monkeypatch.delenv("JEV_API_KEY")
        monkeypatch.setenv("TYPESAFE_API_KEY", "official-key")
        assert resolve_jev_api_key() == "official-key"

    def test_missing_returns_none(self, monkeypatch):
        monkeypatch.delenv("JEV_API_KEY", raising=False)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        assert resolve_jev_api_key() is None

    def test_client_requires_key_without_mock(self, monkeypatch):
        monkeypatch.delenv("JEV_API_KEY", raising=False)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        with pytest.raises(ValueError):
            JevClient()


class TestConfigValidation:
    def test_invalid_packaging_rejected(self):
        with pytest.raises(ValueError):
            JevLightController(StubJevClient(), 15, packaging="bogus")

    def test_invalid_fallback_rejected(self):
        with pytest.raises(ValueError):
            JevLightController(StubJevClient(), 15, fallback="bogus")

    def test_confidence_bounds_enforced(self):
        with pytest.raises(ValueError):
            JevLightController(StubJevClient(), 15, min_confidence=1.5)

    def test_invalid_transport_rejected(self):
        with pytest.raises(ValueError):
            JevClient(transport="carrier-pigeon", api_key="k")
