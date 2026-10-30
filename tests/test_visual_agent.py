from pathlib import Path
from itertools import count

import pytest

from jevlight.controller import JevLightController
from jevlight.jev_client import JevClient, JevResult
from jevlight.visual_agent import VisualAgent
from jevlight.visual_agent import JinanGroupedVisualAgent
from PIL import Image
from tests.test_jevlight_controller import make_observation, phase_answer


class VisualStub(JevClient):
    def __init__(self, fail_perception=False, invalid_confidence=False):
        super().__init__(transport="official", mock=True)
        self.calls = []
        self.fail_perception = fail_perception
        self.invalid_confidence = invalid_confidence

    def evaluate(self, state, questions, assets=None):
        self.calls.append((state, questions, assets))
        if assets:
            if self.fail_perception and len(self.calls) == 2:
                return JevResult(error="camera unavailable")
            return JevResult(answers={key: {
                "type": "choice",
                "choice": "stable" if key.endswith("trend") else "many" if key.startswith("ET") else "none",
                "confidence": float("nan") if self.invalid_confidence else 0.9,
            } for key in questions})
        return JevResult(answers={key: phase_answer("NTST") for key in questions})


def views():
    return [Path(f"camera_{label}.jpg") for label in ("EASTBOUND", "WESTBOUND", "NORTHBOUND", "SOUTHBOUND")]


def test_visual_barrier_routes_only_current_visual_estimates_and_tracks_history():
    client = VisualStub()
    controller = JevLightController(client, 15, agent_mode="jevlight")
    agent = VisualAgent(controller)
    a = make_observation("a", queue_by_phase={"ETWT": 999}, empty=True)
    b = make_observation("b")
    a.lane_relations = {"WT": {"upstream": [{"intersection_id": "b", "lane": "ET"}], "downstream": []}}
    a.topology_available = True
    actions, traces = agent.decide([a, b], {"a": views(), "b": views()}, 0)
    assert actions == {"a": 1, "b": 1}
    assert all(call[2] for call in client.calls[:2])
    assert all(call[2] is None for call in client.calls[2:])
    assert len(client.calls[0][2]) == 4
    assert client.calls[0][0]["previous_views"] == []
    state = client.calls[2][0]
    assert "visual_perception" in state
    assert "cooperative_view" not in state
    assert "current_phase" not in state
    assert "intersection_id" not in state
    assert traces[0]["image_agent"] == "vlalight"
    assert traces[0]["fallback"] is None
    agent.decide([a, b], {"a": views(), "b": views()}, 1)
    second = client.calls[4]
    assert len(second[2]) == 8
    assert "elapsed_s" not in second[0]
    assert len(second[0]["previous_views"]) == 4
    assert client.calls[6][0].keys() == {"visual_perception"}
    assert controller.usage_summary()["requests"] == 8
    with pytest.raises(ValueError, match="increase"):
        agent.decide([a], {"a": views()}, 1)


def test_failed_perception_holds_signal_and_is_not_routed_as_empty():
    client = VisualStub(fail_perception=True)
    controller = JevLightController(client, 15, agent_mode="jevlight")
    agent = VisualAgent(controller)
    a, b = make_observation("a"), make_observation("b")
    a.lane_relations = {"WT": {"upstream": [{"intersection_id": "b", "lane": "ET"}]}}
    actions, traces = agent.decide([a, b], {"a": views(), "b": views()}, 0)
    assert actions == {"a": 1, "b": 0}
    assert traces[1]["fallback"] == "visual_perception_failed"
    assert traces[1]["error"] == "camera unavailable"
    assert "current_phase" not in client.calls[2][0]
    assert "cooperative_view" not in client.calls[2][0]
    assert len(client.calls) == 3
    assert controller.usage_summary()['failures'] == 1


def test_visual_requests_do_not_depend_on_simulator_traffic_state(monkeypatch):
    monkeypatch.setattr("jevlight.visual_agent.uuid.uuid4", lambda: "fixed-camera-reference")
    clients = [VisualStub(), VisualStub()]
    for index, client in enumerate(clients):
        observation = make_observation()
        observation.empty = bool(index)
        for lane in observation.lanes.values():
            lane.queue = index * 987
            lane.approaching = index * 654
            lane.avg_wait = index * 321
            lane.occupancy = index * .9
            lane.cells = [index * 123] * len(lane.cells)
            lane.llmlight_cells = [index * 456] * len(lane.llmlight_cells)
            lane.vehicles = {"hidden-simulator-vehicle": index}
        agent = VisualAgent(JevLightController(client, 15))
        for step in (0, 1):
            agent.decide([observation], {"i0": views()}, step)
    # Both stages and their visual history must be invariant to hidden traffic.
    assert clients[0].calls == clients[1].calls


def test_nonfinite_perception_is_rejected_without_decision_call():
    client = VisualStub(invalid_confidence=True)
    agent = VisualAgent(JevLightController(client, 15))
    actions, traces = agent.decide([make_observation()], {"i0": views()}, 0)
    assert actions == {"i0": 0}
    assert len(client.calls) == 1
    assert traces[0]["fallback"] == "visual_perception_failed"


def test_visual_agent_requires_four_views_and_image_capable_transport():
    client = VisualStub()
    agent = VisualAgent(JevLightController(client, 15))
    with pytest.raises(ValueError, match="four"):
        agent.decide([make_observation()], {"i0": Path("composite.jpg")}, 0)
    client.transport = "mcp"
    with pytest.raises(ValueError, match="image-capable"):
        agent.decide([make_observation()], {"i0": views()}, 0)


def test_local_visual_agent_uses_both_stages_and_camera_history():
    client = VisualStub()
    client.transport, client.model = "local", "Rover00/WeMM-JEV"
    agent = VisualAgent(JevLightController(client, 15))
    for step in (0, 1):
        _, traces = agent.decide([make_observation()], {"i0": views()}, step)
        assert traces[0]["fallback"] is None
    assert [len(call[2] or {}) for call in client.calls] == [4, 0, 8, 0]


def real_views(tmp_path):
    paths = []
    for view in ('EASTBOUND', 'WESTBOUND', 'NORTHBOUND', 'SOUTHBOUND'):
        path = tmp_path / f'camera_{view}.png'
        Image.new('RGB', (384, 720), (120, 120, 120)).save(path)
        paths.append(path)
    return paths


def test_grouped_visual_barrier_counts_every_request_and_preserves_all_movements(tmp_path):
    paths = real_views(tmp_path)
    client = VisualStub()
    controller = JevLightController(client, 15)
    agent = JinanGroupedVisualAgent(controller)
    a, b = make_observation('a'), make_observation('b')
    a.lane_relations = {'WT': {'upstream': [{'intersection_id': 'b', 'lane': 'ET'}]}}
    for step in (0, 1):
        actions, traces = agent.decide([a, b], {'a': paths, 'b': paths}, step)
        assert actions == {'a': 1, 'b': 1}
        calls = client.calls[step * 6:(step + 1) * 6]
        assert all(call[2] for call in calls[:4])
        assert all(call[2] is None for call in calls[4:])
        assert all(len(call[1]) == 12 for call in calls[:4])
        assert all(len(call[2]) == (4 if step == 0 else 8) for call in calls[:4])
        for state, questions, assets in calls[:4]:
            expected = {key.split('_')[0] for key in questions}
            assert expected in ({'NT', 'NL', 'ST', 'SL'}, {'ET', 'EL', 'WT', 'WL'})
            assert {v['movement'] for v in state['current_views']} == expected
            assert {v['image'] for group in ('current_views', 'previous_views')
                    for v in state[group]} == set(assets)
        assert set(calls[4][0]['visual_perception']) == {'NT', 'NL', 'ST', 'SL', 'ET', 'EL', 'WT', 'WL'}
        assert 'cooperative_view' not in calls[4][0]
        assert all(t['image_agent'] == 'vlalight-grouped' and len(t['perception_requests']) == 2 for t in traces)
    assert controller.usage_summary()['requests'] == 12


@pytest.mark.parametrize('error', [True, False])
def test_one_failed_or_incomplete_group_holds_whole_junction_and_counts_once(tmp_path, error):
    class PartialStub(VisualStub):
        def evaluate(self, state, questions, assets=None):
            if assets and 'NT_demand' in questions:
                if error:
                    self.calls.append((state, questions, assets))
                    return JevResult(error='one image group failed')
                result = super().evaluate(state, questions, assets)
                result.answers.pop('NL_queue')
                return result
            return super().evaluate(state, questions, assets)

    client = PartialStub()
    controller = JevLightController(client, 15)
    agent = JinanGroupedVisualAgent(controller)
    actions, traces = agent.decide([make_observation()], {'i0': real_views(tmp_path)}, 0)
    assert actions == {'i0': 0}
    assert len(client.calls) == 2
    assert controller.usage_summary()['requests'] == 2
    assert controller.usage_summary()['failures'] == 1
    assert traces[0]['decision_state'] is None
    assert traces[0]['fallback'] == 'visual_perception_failed'


def test_grouped_requests_and_actions_are_invariant_to_hidden_traffic(tmp_path, monkeypatch):
    paths = real_views(tmp_path)
    clients = [VisualStub(), VisualStub()]
    for index, client in enumerate(clients):
        refs = count()
        monkeypatch.setattr('jevlight.visual_agent.uuid.uuid4', lambda: str(next(refs)))
        observation = make_observation(empty=bool(index))
        for lane in observation.lanes.values():
            lane.queue, lane.approaching, lane.avg_wait = index * 999, index * 777, index * 555
            lane.occupancy, lane.cells, lane.llmlight_cells = index * .8, [index * 123], [index * 456]
            lane.vehicles = {'hidden': index}
        agent = JinanGroupedVisualAgent(JevLightController(client, 15))
        for step in (0, 1):
            actions, _ = agent.decide([observation], {'i0': paths}, step)
            assert actions == {'i0': 1}
    assert clients[0].calls == clients[1].calls


def test_cooperation_routes_current_visual_answers_without_simulator_measurements():
    client = VisualStub()
    agent = VisualAgent(JevLightController(client, 15), cooperation=True)
    a, b = make_observation('a'), make_observation('b')
    a.lane_relations = {'WT': {
        'upstream': [{'intersection_id': 'b', 'lane': 'ET'}] * 2,
        'downstream': [{'intersection_id': 'missing', 'lane': 'NT'}],
    }}
    b.current_phase = 'ELWL'
    b.lanes['ET'].queue = 918273
    _, traces = agent.decide([a, b], {'a': views(), 'b': views()}, 0)
    state = client.calls[2][0]
    co = state['cooperative_view']
    assert co['possible_connections']['WT']['upstream'] == [
        {'neighbour': 'neighbour_1', 'movement': 'ET'}]
    assert co['neighbours']['neighbour_1']['visual_perception']['ET']['demand']['estimate'] == 'many'
    assert co['neighbours']['neighbour_2']['visual_perception'] is None
    assert len(co['neighbours']) == 2
    assert 'current_phase' not in str(state) and '918273' not in str(state)
    assert 'intersection_id' not in str(state)
    assert all(t['visual_cooperation'] for t in traces)


def test_cooperation_does_not_reuse_failed_neighbour_or_hidden_signal_state(monkeypatch):
    monkeypatch.setattr('jevlight.visual_agent.uuid.uuid4', lambda: 'fixed-image-reference')
    clients = [VisualStub(fail_perception=True), VisualStub(fail_perception=True)]
    for index, client in enumerate(clients):
        a, b = make_observation('a'), make_observation('b')
        a.lane_relations = {'WT': {'upstream': [{'intersection_id': 'b', 'lane': 'ET'}]}}
        b.current_phase = 'ETWT' if index else 'NLSL'
        b.yellow_time = 5 + index * 4321
        b.empty = bool(index)
        for lane in b.lanes.values():
            lane.queue, lane.approaching, lane.avg_wait = index * 999, index * 777, index * 555
        agent = VisualAgent(JevLightController(client, 15), cooperation=True)
        agent.decide([a, b], {'a': views(), 'b': views()}, 0)
        co = client.calls[2][0]['cooperative_view']
        assert co['neighbours']['neighbour_1']['visual_perception'] is None
    assert clients[0].calls == clients[1].calls
