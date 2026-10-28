"""LLMLight/CoLLMLight baseline unit tests (no network, no SUMO)."""

from __future__ import annotations

import json

from baselines.llmlight.controller import (
    DEFAULT_LLM_PATH,
    CoLLMLightController,
    LanguageModelAdapter,
    LLMLightController,
    LLMResult,
    extract_collmlight_result,
    extract_signal,
    resolve_llmlight_model,
)
from baselines.llmlight.prompts import (
    LLMLIGHT_SYSTEM_PROMPT,
    llmlight_state2text,
    llmlight_user_prompt,
)
from jevlight.observation import IntersectionObservation, LaneObservation, rank_phases


PHASES = ["WT_ET", "NT_ST", "WL_EL", "NL_SL"]


def make_lane(queue=0.0, cells=(0, 0, 0, 0), queue_cells=(0,) * 10, moving=(0,) * 10,
              waiting=0.0, vehicles=(), occupancy=0.0, road_length=300.0):
    lane = LaneObservation()
    lane.queue = float(queue)
    lane.llmlight_cells = list(cells)
    lane.queue_cells = list(queue_cells)
    lane.cells = list(moving)
    lane.avg_wait = float(waiting)
    lane.vehicles = {vehicle: 0 for vehicle in vehicles}
    lane.occupancy = float(occupancy)
    lane.road_length = float(road_length)
    return lane


def make_observation(intersection_id="i0", empty=False, current_phase="WT_ET",
                     lanes=None):
    if lanes is None:
        lanes = {lane: make_lane() for lane in (
            "NT", "NL", "NR", "ST", "SL", "SR",
            "ET", "EL", "ER", "WT", "WL", "WR",
        )}
    return IntersectionObservation(
        intersection_id=intersection_id,
        lanes=lanes,
        phases=list(PHASES),
        neighbours=[],
        empty=empty,
        current_phase=current_phase,
    )


class StubAdapter(LanguageModelAdapter):
    """Replays scripted LLMResults without any backend."""

    def __init__(self, results):
        super().__init__(mock=True)
        self.results = list(results)
        self.calls = []

    def batch_complete(self, system_prompt, prompts):
        self.calls.append(list(prompts))
        return [self.results.pop(0) if self.results else LLMResult(content="")
                for _ in prompts]


class TestModelResolution:
    def test_local_provider_passthrough(self):
        assert resolve_llmlight_model("local", "LLMLight") == "LLMLight"

    def test_siliconflow_default_model(self):
        assert resolve_llmlight_model("siliconflow", "LLMLight") == DEFAULT_LLM_PATH

    def test_siliconflow_prefixing(self):
        assert resolve_llmlight_model("siliconflow", "foo") == "siliconflow/foo"
        assert resolve_llmlight_model("siliconflow", "siliconflow/foo") == "siliconflow/foo"

    def test_unknown_provider(self):
        import pytest

        with pytest.raises(ValueError):
            resolve_llmlight_model("other", "foo")


class TestParsers:
    def test_extract_signal_takes_last_tag(self):
        response = "step <signal>ETWT</signal> more <signal>NTST</signal>"
        assert extract_signal(response) == "NTST"

    def test_extract_signal_rejects_unknown(self):
        assert extract_signal("<signal>FOO</signal>") is None
        assert extract_signal("") is None
        assert extract_signal(None) is None

    def test_extract_collmlight_result_fenced(self):
        response = '```json\n{"signal": "ELWL", "reason": "r", "used_atr": 1}\n```'
        assert extract_collmlight_result(response) == {
            "signal": "ELWL", "reason": "r", "used_atr": 1,
        }

    def test_extract_collmlight_result_case_insensitive_keys(self):
        response = '{"Signal": "NLSL"}'
        assert extract_collmlight_result(response)["signal"] == "NLSL"

    def test_extract_collmlight_result_garbage(self):
        assert extract_collmlight_result("no json here") == {
            "signal": None, "reason": None, "used_atr": 0,
        }


class TestMockResponses:
    def test_structured_json_mock_follows_priority_table(self):
        adapter = LanguageModelAdapter(mock=True)
        prompt = "table\n|1|NTST|3.4|\n|2|ETWT|1.0|\nanswer in structured JSON format"
        assert json.loads(adapter._mock_response(prompt))["signal"] == "NTST"

    def test_atr_mock(self):
        adapter = LanguageModelAdapter(mock=True)
        assert "Identify Critical Lanes" in adapter._mock_response(
            "Advance Traffic Reasoning prompt"
        )

    def test_plain_mock_defaults_to_etwt(self):
        adapter = LanguageModelAdapter(mock=True)
        # The LLMLight state text has no priority table, so the mock falls
        # back to ETWT — exactly the source behavior.
        prompt = llmlight_user_prompt(
            llmlight_state2text(make_observation().lanes)
        )
        assert adapter._mock_response(prompt) == (
            "Traffic demand favors this phase. <signal>ETWT</signal>"
        )


class TestPrompts:
    def test_state2text_lists_all_four_phases(self):
        text = llmlight_state2text(make_observation().lanes)
        for phase in ("ETWT", "NTST", "ELWL", "NLSL"):
            assert f"Signal: {phase}" in text
        assert "Segment 1" in text and "Segment 3" in text

    def test_user_prompt_carries_the_signal_tag_requirement(self):
        prompt = llmlight_user_prompt("STATE")
        assert "<signal>YOUR_CHOICE</signal>" in prompt
        assert "STATE" in prompt


class TestLLMLightController:
    def test_mock_decide_emits_etwt(self):
        controller = LLMLightController(LanguageModelAdapter(mock=True), 15)
        observation = make_observation()
        actions, traces = controller.decide([observation], 0)
        assert actions["i0"] == 0  # WT_ET == canonical ETWT
        assert traces[0]["controller"] == "llmlight"
        assert traces[0]["signal"] == "ETWT"
        assert traces[0]["fallback"] is None
        assert traces[0]["system_prompt"] == LLMLIGHT_SYSTEM_PROMPT
        assert controller.usage_summary()["requests"] == 1

    def test_error_falls_back_to_previous_signal(self):
        controller = LLMLightController(
            StubAdapter([
                LLMResult(content="", error="ConnectionError: down"),
                LLMResult(content="", error="ConnectionError: down"),
            ]),
            15,
        )
        observation = make_observation()
        actions, traces = controller.decide([observation], 0)
        assert traces[0]["signal"] == "ETWT"  # from current_phase WT_ET
        assert traces[0]["fallback"] == "previous_signal_after_request_failure"
        assert actions["i0"] == 0

        # The failed step still commits ETWT, so the next failure keeps it.
        actions, traces = controller.decide([observation], 1)
        assert traces[0]["signal"] == "ETWT"
        assert traces[0]["fallback"] == "previous_signal_after_request_failure"
        assert controller.usage_summary()["failures"] == 2

    def test_unparseable_response_falls_back_to_etwt(self):
        controller = LLMLightController(StubAdapter([LLMResult(content="no tag")]), 15)
        _, traces = controller.decide([make_observation()], 0)
        assert traces[0]["signal"] == "ETWT"
        assert traces[0]["fallback"] == "ETWT"

    def test_usage_summary_accounts_failures_and_tokens(self):
        controller = LLMLightController(
            StubAdapter([
                LLMResult(content="<signal>NTST</signal>",
                          prompt_tokens=10, completion_tokens=5, latency=0.5),
            ]),
            15,
        )
        controller.decide([make_observation()], 0)
        summary = controller.usage_summary()
        assert summary["requests"] == 1
        assert summary["failures"] == 0
        assert summary["input_tokens"] == 10
        assert summary["output_tokens"] == 5
        assert summary["latency_mean_s"] == 0.5
        assert summary["latency_max_s"] == 0.5
        assert summary["rate_limited"] == 0


class TestCoLLMLightController:
    def test_active_junction_runs_atr_then_reactive(self):
        lanes = {
            lane: make_lane() for lane in (
                "NT", "NL", "NR", "ST", "SL", "SR",
                "ET", "EL", "ER", "WT", "WL", "WR",
            )
        }
        lanes["ET"].queue_cells[0] = 3.0
        lanes["ET"].queue = 3.0
        lanes["ET"].avg_wait = 10.0
        observation = make_observation(lanes=lanes)
        controller = CoLLMLightController(LanguageModelAdapter(mock=True), 15)
        actions, traces = controller.decide([observation], 0)
        # The mock's structured-JSON answer follows the reactive prompt's
        # local priority table, i.e. the top of rank_phases.
        expected = rank_phases(observation, 15)[0][0]
        assert traces[0]["signal"] == expected
        assert traces[0]["used_atr"] == 0
        assert "Advance Traffic Reasoning" in traces[0]["atr_prompt"]
        assert "structured JSON format" in traces[0]["reactive_prompt"]
        assert actions["i0"] == controller._phase_to_action(observation, expected)
        assert controller.usage_summary()["requests"] == 2  # ATR + reactive

    def test_empty_junction_decides_locally_without_llm(self):
        controller = CoLLMLightController(LanguageModelAdapter(mock=True), 15)
        observation = make_observation(empty=True)
        actions, traces = controller.decide([observation], 0)
        expected = rank_phases(observation, 15)[0][0]
        assert actions["i0"] == controller._phase_to_action(observation, expected)
        assert traces == []
        assert controller.usage_summary()["requests"] == 0

    def test_invalid_response_keeps_previous_signal(self):
        adapter = StubAdapter([
            LLMResult(content="ATR answer"),
            LLMResult(content="not json"),
        ])
        controller = CoLLMLightController(adapter, 15)
        _, traces = controller.decide([make_observation()], 0)
        assert traces[0]["signal"] == "ETWT"
        assert traces[0]["fallback"] == "previous_signal_after_invalid_response"

    def test_transition_history_survives_two_steps(self):
        adapter = StubAdapter([
            LLMResult(content="ATR"),
            LLMResult(content='{"signal": "NTST", "reason": "r"}'),
            LLMResult(content="ATR"),
            LLMResult(content='{"signal": "ETWT", "reason": "r"}'),
        ])
        controller = CoLLMLightController(adapter, 15)
        lanes = {
            lane: make_lane() for lane in (
                "NT", "NL", "NR", "ST", "SL", "SR",
                "ET", "EL", "ER", "WT", "WL", "WR",
            )
        }
        lanes["ET"].vehicles = {"v1": 0, "v2": 0}
        observation = make_observation(lanes=lanes)
        actions, _ = controller.decide([observation], 0)
        assert actions["i0"] == 1  # NT_ST
        assert controller.previous_observations["i0"] is observation
        actions, _ = controller.decide([observation], 1)
        assert actions["i0"] == 0  # WT_ET
        assert len(controller.traffic_state_logs["i0"]) == 1

    def test_think_tag_stripped_from_atr(self):
        from baselines.llmlight.controller import _after_think_tag

        assert _after_think_tag("<think>reasoning</think>answer") == "answer"
        assert _after_think_tag("plain") == "plain"
