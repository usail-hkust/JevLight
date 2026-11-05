from copy import deepcopy
import json
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

from jevlight.vlalight_images import (compose_views, tls_camera_info, VLALightRenderer,
                                    configure_gltf_loader, lane_arrow_data, VIEW_LABELS)
from scripts.benchmark_vlalight_jev import (
    OPEN_VISION_MODELS, build_cases, validate_summary, aggregate,
)
from scripts.fetch_vlalight_renderer import REVISION, blob_hash, selected


def test_renderer_refuses_missing_gltf_before_loading_scene(monkeypatch, tmp_path):
    import sys
    source = tmp_path / 'VLALight'
    renderer = VLALightRenderer(source, {"template": "Jinan", "road_net": "3_4"},
                               'network.xml', tmp_path / 'frames')
    renderer.scene_dir.mkdir(parents=True)
    (tmp_path / 'renderer-manifest.json').write_text(
        json.dumps({"repository": "usail-hkust/VLALight", "revision": REVISION}))
    monkeypatch.setitem(sys.modules, 'gltf', None)
    with pytest.raises(RuntimeError, match='Refusing the Assimp fallback'):
        renderer.__enter__()
    assert renderer.renderer is None


def test_renderer_registers_gltf_even_when_another_loader_was_selected(monkeypatch):
    import sys
    from types import ModuleType
    gltf = ModuleType('gltf')
    gltf.__version__ = '1.3.0'
    loader_module = ModuleType('gltf._loader')
    loader_module.GltfLoader = object()
    events = []
    registry = SimpleNamespace(register_type=lambda loader: events.append(('loader', loader)))
    core = ModuleType('panda3d.core')
    core.LoaderFileTypeRegistry = SimpleNamespace(getGlobalPtr=lambda: registry)
    core.BamCache = SimpleNamespace(getGlobalPtr=lambda: SimpleNamespace(
        setCacheModels=lambda active: events.append(('disk_models', active))))
    core.ModelPool = SimpleNamespace(releaseAllModels=lambda: events.append(('clear_pool',)))
    monkeypatch.setitem(sys.modules, 'gltf', gltf)
    monkeypatch.setitem(sys.modules, 'gltf._loader', loader_module)
    monkeypatch.setitem(sys.modules, 'panda3d.core', core)
    assert configure_gltf_loader() == {"asset_loader": "panda3d-gltf", "asset_loader_version": "1.3.0",
                                       "asset_model_cache": "memory-only-v1"}
    assert events == [('loader', loader_module.GltfLoader), ('disk_models', False), ('clear_pool',)]


def test_camera_labels_follow_vehicle_motion_without_subscriptions():
    shapes = {"e_0": [(0, 0), (20, 0)], "n_0": [(0, 0), (0, 20)],
              "w_0": [(20, 0), (0, 0)], "s_0": [(0, 20), (0, 0)]}
    conn = SimpleNamespace(
        trafficlight=SimpleNamespace(getControlledLinks=lambda _: [((lane, "out", "via"),) for lane in shapes]),
        lane=SimpleNamespace(getEdgeID=lambda lane: lane[0], getShape=shapes.__getitem__),
        edge=SimpleNamespace(getAngle={"n": 0, "e": 90, "s": 180, "w": 270}.__getitem__),
    )
    init, labels, centers = tls_camera_info(conn, ["i1"])
    assert labels["i1"] == ["NORTHBOUND", "EASTBOUND", "SOUTHBOUND", "WESTBOUND"]
    assert centers["i1"] == (5, 5)
    assert init["tls"]["i1"]["in_roads_heading"]["e"] == 90


def test_composite_preserves_crop_and_all_four_views():
    images = []
    for value in (50, 100, 150, 200):
        view = np.zeros((1080, 1920, 3), dtype=np.uint8)
        view[:, 768:1344] = value
        images.append(view)
    output = compose_views(images, ["N", "E", "S", "W"])
    assert output.size == (768, 1440)
    for x, y, value in [(192, 360, 50), (576, 360, 100), (192, 1080, 150), (576, 1080, 200)]:
        assert output.getpixel((x, y)) == (value, value, value)


@pytest.mark.parametrize('draw_stage', [0, 1, 2])
def test_capture_reads_current_batch_after_camera_and_vehicle_updates(tmp_path, draw_stage):
    """A finished draw can still contain a previous camera's queued scene."""
    from collections import deque

    class Pipeline:
        def __init__(self):
            self.pending = deque([0] * draw_stage)
            self.current = self.visible = 0

        def getThreadingModel(self):
            return SimpleNamespace(getDrawStage=lambda: draw_stage)

        def renderFrame(self):
            self.pending.append(self.current)
            self.visible = self.pending.popleft()

        def syncFrame(self):
            pass  # Waiting for Draw does not advance the pipeline.

    engine = Pipeline()
    identities = ['first', 'second']
    batch = [0]

    def collect(_):
        identity = identities[batch[0]]
        return {f'{identity}_{i}': {'junction_front_all':
                    np.full((108, 192, 3), engine.visible, dtype=np.uint8)}
                for i in range(4)}

    def step(*args, **kwargs):
        engine.current = 80 + batch[0] * 80
        engine.renderFrame()

    renderer = VLALightRenderer(tmp_path, {'template': 'Jinan', 'road_net': '3_4'},
                               'network.xml', tmp_path)
    renderer.labels = {identity: list(VIEW_LABELS) for identity in identities}
    renderer.centers = dict.fromkeys(identities, (0, 0))
    renderer.renderer = SimpleNamespace(
        get_batch_info=lambda: {'total_batches': 2},
        switch_to_batch=lambda index: batch.__setitem__(0, index),
        get_current_batch_tls_ids=lambda: [identities[batch[0]]], step=step,
        _showbase_instance=SimpleNamespace(graphicsEngine=engine),
        scene_sync=SimpleNamespace(collect_sensors=collect, _current_batch_tls_elements=lambda: {}))
    conn = SimpleNamespace(vehicle=SimpleNamespace(getIDList=lambda: []))
    for decision_step in (0, 1):
        paths = renderer.capture(conn, identities, decision_step, separate_views=True)
        for index, identity in enumerate(identities):
            from PIL import Image
            with Image.open(paths[identity][0]) as picture:
                assert all(abs(value - (80 + index * 80)) <= 1
                           for value in picture.getpixel((192, 360)))


def test_image_titles_use_vlalight_vehicle_travel_direction():
    assert VIEW_LABELS == {'NORTHBOUND': 'NORTH', 'SOUTHBOUND': 'SOUTH',
                           'EASTBOUND': 'EAST', 'WESTBOUND': 'WEST'}


def test_direction_titles_fit_enlarged_strip_without_shifting_road():
    views = [np.full((1080, 1920, 3), 120, dtype=np.uint8)] * 4
    output = compose_views(views, list(VIEW_LABELS))
    for x, y in [(0, 0), (384, 0), (0, 720), (384, 720)]:
        tile = np.asarray(output.crop((x, y, x + 384, y + 720)))
        text_y, text_x = np.where((tile[:, :, 0] > 180) & (tile[:, :, 1] > 180)
                                  & (tile[:, :, 2] < 80))
        assert text_y.max() - text_y.min() + 1 >= 20
        assert text_y.max() < 42 and text_x.max() < 384
        assert (tile[41] == 0).all()
        assert (tile[42:] == 120).all()


@pytest.mark.parametrize('dataset,intersections', [('Jinan/3_4', 12), ('Hangzhou/4_4', 16),
                                                 ('NewYork/28_7', 196)])
def test_static_arrows_match_all_controlled_lane_permissions(dataset, intersections):
    data = Path(__file__).resolve().parents[1] / 'data' / dataset
    arrows = lane_arrow_data(next(data.glob('roadnet*.net.xml')))
    assert len(arrows) == intersections * 12
    for shape, turn, width, index, count in arrows:
        assert len(shape) >= 2 and width > 0 and count == 3
        assert turn == ('right', 'straight', 'left')[index]


def test_manifest_fetch_selects_renderer_without_training_or_accident_models():
    assert selected("VLALight/TransSimHub/tshub/tshub_env3d/vis3d_renderer/tshub_render.py")
    assert selected("VLALight/TransSimHub/examples/NewYork/3d_assets/map.glb")
    assert not selected("training/checkpoint.safetensors")
    assert not selected("VLALight/TransSimHub/tshub/tshub_env3d/_assets_3d/vehicles_low_poly/event/crash_vehicle.glb")
    assert blob_hash(b"test\n") == "9daeafb9864cf43055ae93beb0afd6c7d144bfa4"


def test_plan_contains_only_the_seven_selected_traffic_flows():
    cases = build_cases()
    assert len(cases) == 7
    assert {c["id"] for c in cases} == {
        "jinan/anon_3_4_jinan_real",
        "jinan/anon_3_4_jinan_real_2000",
        "jinan/anon_3_4_jinan_real_2500",
        "hangzhou/anon_4_4_hangzhou_real",
        "hangzhou/anon_4_4_hangzhou_real_5816",
        "newyork/anon_28_7_newyork_real_double",
        "newyork/anon_28_7_newyork_real_triple",
    }
    assert {c["horizon_s"] for c in cases} == {3600}
    assert sum(c["image_requests_per_seed"] for c in cases) * 3 == 331200


def valid_image_summary(case):
    return {**{field: case[field] for field in ("dataset", "traffic_file", "traffic_sha256", "roadnet_sha256")},
            "seed": 1, "control_interval_s": 15, "final/end_time": case["horizon_s"],
            "image_decisions": True, "image_renderer": "vlalight", "mock_jev": False,
            "jev_transport": "official", "jev_model": "jev-1.14.0",
            "renderer_metadata": {"revision": REVISION},
            "fallback_count": 0, "jev": {"requests": case["image_requests_per_seed"], "failures": 0}}


def test_two_stage_image_agent_requires_two_requests_per_intersection():
    case = build_cases()[0]
    summary = {**valid_image_summary(case), "image_agent": "vlalight",
               "visual_prompt_version": "vlalight-two-stage-v2",
               "jev": {"requests": case["image_requests_per_seed"] * 2, "failures": 0}}
    assert validate_summary(summary, case, 1, "jev-image") == "complete"
    summary["jev"]["requests"] -= 1
    assert validate_summary(summary, case, 1, "jev-image") == "incomplete_requests"


def test_grouped_agent_requires_three_requests_and_rejects_uncalibrated_scenes():
    case = next(c for c in build_cases() if c['dataset'] == 'jinan')
    summary = {**valid_image_summary(case), 'image_agent': 'vlalight-grouped',
               'visual_prompt_version': 'vlalight-jinan-opposite-v3',
               'jev': {'requests': case['image_requests_per_seed'] * 3, 'failures': 0}}
    assert validate_summary(summary, case, 1, 'jev-image') == 'complete'
    assert validate_summary({**summary, 'visual_prompt_version': 'vlalight-jinan-opposite-v1'},
                            case, 1, 'jev-image') == 'invalid_method'
    summary['jev']['requests'] -= 1
    assert validate_summary(summary, case, 1, 'jev-image') == 'incomplete_requests'
    other = next(c for c in build_cases() if c['dataset'] == 'hangzhou')
    assert validate_summary({**valid_image_summary(other), 'image_agent': 'vlalight-grouped'},
                            other, 1, 'jev-image') == 'invalid_method'


def test_grouped_smoke_plan_counts_real_api_evaluations(monkeypatch, tmp_path):
    import scripts.benchmark_vlalight_jev as benchmark
    case = next(c for c in build_cases() if c['dataset'] == 'jinan')
    monkeypatch.setattr(benchmark, 'build_cases', lambda: [case])
    monkeypatch.setattr('sys.argv', ['benchmark', '--method', 'smoke', '--image_agent', 'vlalight-grouped',
                                   '--seeds', '1', '--output', str(tmp_path)])
    benchmark.main()
    plan = json.loads((tmp_path / 'plan_smoke-vlalight-grouped.json').read_text())
    assert plan['estimated_image_requests'] == case['intersections'] * 2 * 3


def test_grouped_runtime_rejects_another_camera_profile_before_running():
    from run_jevlight import parse_args, run
    args = parse_args(['--image_agent', 'vlalight-grouped', '--image_decisions',
                       '--image_renderer', 'vlalight', '--jev_transport', 'official',
                       '--dataset', 'hangzhou', '--mock_jev', '--count', '15'])
    with pytest.raises(ValueError, match='calibrated Jinan'):
        run(args)


def test_visual_smoke_plan_estimates_both_stages(monkeypatch, tmp_path):
    import scripts.benchmark_vlalight_jev as benchmark
    case = build_cases()[0]
    monkeypatch.setattr(benchmark, "build_cases", lambda: [case])
    monkeypatch.setattr("sys.argv", ["benchmark", "--method", "smoke", "--image_agent", "vlalight",
                                     "--seeds", "1", "--output", str(tmp_path)])
    benchmark.main()
    plan = json.loads((tmp_path / "plan_smoke-vlalight.json").read_text())
    assert plan["cases"][0]["image_requests_per_seed"] == case["intersections"] * 2
    assert plan["estimated_image_requests"] == case["intersections"] * 4


def test_plan_can_select_one_exact_scenario_and_seed(monkeypatch, tmp_path):
    import scripts.benchmark_vlalight_jev as benchmark
    cases = build_cases()
    monkeypatch.setattr(benchmark, "build_cases", lambda: cases)
    monkeypatch.setattr("sys.argv", ["benchmark", "--method", "jev-image", "--image_agent", "vlalight",
                                     "--cases", "jinan/anon_3_4_jinan_real", "--seeds", "1",
                                     "--output", str(tmp_path)])
    benchmark.main()
    plan = json.loads((tmp_path / "plan_jev-image-vlalight.json").read_text())
    assert plan["seeds"] == [1]
    assert [case["id"] for case in plan["cases"]] == ["jinan/anon_3_4_jinan_real"]
    assert plan["estimated_image_requests"] == plan["cases"][0]["image_requests_per_seed"] * 2


def test_incomplete_mock_and_fallback_runs_cannot_be_scores():
    case = build_cases()[0]
    summary = valid_image_summary(case)
    assert validate_summary(summary, case, 1, "jev-image") == "complete"
    for change, status in [({"mock_jev": True}, "invalid_method"),
                           ({"image_agent": "unknown"}, "invalid_method"),
                           ({"jev_model": "jev-latest"}, "invalid_method"),
                           ({"renderer_metadata": {"revision": "changed"}}, "invalid_method"),
                           ({"final/end_time": 3599}, "incomplete_horizon"),
                           ({"traffic_sha256": "changed"}, "invalid_metadata"),
                           ({"fallback_count": 1}, "degraded_fallbacks")]:
        assert validate_summary({**summary, **change}, case, 1, "jev-image") == status
    failed = deepcopy(summary)
    failed["jev"]["failures"] = 1
    assert validate_summary(failed, case, 1, "jev-image") == "degraded_fallbacks"
    assert aggregate([{"case": case["id"], "summary": summary, "status": "smoke_only"}]) == {}


@pytest.mark.parametrize("method", OPEN_VISION_MODELS)
def test_open_vision_models_use_local_transport_and_shared_score_contract(method):
    case = build_cases()[0]
    summary = {**valid_image_summary(case), "jev_transport": "local",
               "jev_model": OPEN_VISION_MODELS[method]}
    assert validate_summary(summary, case, 1, method) == "complete"
    assert validate_summary({**summary, "jev_transport": "official"}, case, 1, method) == "invalid_method"
    assert validate_summary({**summary, "jev_model": "text-only-open-jev"}, case, 1, method) == "invalid_method"


def test_all_four_networks_have_matching_scene_assets(tmp_path):
    from jevlight.config import DATASETS
    for dataset in ("jinan", "hangzhou", "newyork", "newyork_16x3"):
        renderer = VLALightRenderer(tmp_path, DATASETS[dataset], "road.net.xml", tmp_path)
        assert renderer.scene_dir.name == "3d_assets"


def test_report_does_not_trust_mock_runs_labelled_as_real_scores(tmp_path):
    from scripts.report_vlalight_jev import write_report
    case = build_cases()[0]
    plan = {"method": "jev-image", "seeds": [1], "cases": [case],
            "estimated_image_requests": case["image_requests_per_seed"]}
    (tmp_path / "plan_jev-image.json").write_text(json.dumps(plan))
    summary = {**valid_image_summary(case), "mock_jev": True}
    (tmp_path / "jev-image.json").write_text(json.dumps({
        "plan": plan, "runs": [{"case": case["id"], "seed": 1,
                                  "status": "complete", "summary": summary}]}))
    write_report(tmp_path)
    report = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Official Jev 1.14.0: 0/1" in report
    assert "WeMM-JEV-27B (open weights): 0/1" in report
    assert "pending | pending | pending" in report


def test_report_reads_the_isolated_visual_agent_plan(tmp_path):
    from scripts.report_vlalight_jev import write_report
    case = build_cases()[0]
    plan = {"method": "jev-image", "image_agent": "vlalight", "seeds": [1],
            "cases": [case], "estimated_image_requests": case["image_requests_per_seed"] * 2}
    (tmp_path / "plan_jev-image-vlalight.json").write_text(json.dumps(plan))
    write_report(tmp_path, "vlalight")
    report = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Selected image agent: `vlalight`." in report
    assert "plan_jev-image-vlalight.json" in report
    assert "four current and four previous" in report


def test_api_preflight_failure_preserves_saved_results(monkeypatch, tmp_path):
    import scripts.benchmark_vlalight_jev as benchmark
    case = build_cases()[0]
    result_path = tmp_path / "jev-image.json"
    result_path.write_text('{"saved": true}')
    monkeypatch.setattr(benchmark, "build_cases", lambda: [case])
    monkeypatch.setattr(benchmark, "check_image_api", lambda *a, **kw: "HTTP 451")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(benchmark.subprocess, "run", lambda *a, **kw: pytest.fail("SUMO started despite blocked API"))
    monkeypatch.setattr("sys.argv", ["benchmark", "--execute", "--resume", "--output", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        benchmark.main()
    assert error.value.code == 2
    assert json.loads(result_path.read_text()) == {"saved": True}


def test_api_preflight_records_region_block_without_a_simulation(monkeypatch, tmp_path):
    import scripts.benchmark_vlalight_jev as benchmark
    from jevlight.jev_client import JevClient, JevResult
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setattr(JevClient, "evaluate", lambda *a, **kw: JevResult(error="HTTP 451: region unavailable"))
    assert "451" in benchmark.check_image_api(tmp_path)
    record = json.loads((tmp_path / "api_preflight.json").read_text())
    assert record["status"] == "blocked_api"
    assert record["input_tokens"] == 0


def test_visual_agent_preflight_sends_eight_direction_and_history_images(monkeypatch, tmp_path):
    import scripts.benchmark_vlalight_jev as benchmark
    from jevlight.jev_client import JevClient, JevResult
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    captured = []

    def evaluate(self, state, questions, assets=None):
        captured.append((state, questions, assets))
        return JevResult(answers={"probe": {"type": "choice", "choice": "readable"}},
                         model="jev-1.14.0")

    monkeypatch.setattr(JevClient, "evaluate", evaluate)
    assert benchmark.check_image_api(tmp_path, retries=0, image_agent="vlalight") is None
    state, questions, assets = captured[0]
    assert len(assets) == 8
    assert len(state["current_views"]) == len(state["previous_views"]) == 4
    assert {view["view"] for view in state["current_views"]} == {
        "EASTBOUND", "WESTBOUND", "NORTHBOUND", "SOUTHBOUND"}
    assert questions["probe"]["criteria"] == {
        "readable": "The labelled camera frames are present and readable.",
        "unreadable": "The camera frames are absent or unreadable.",
    }


def test_open_model_preflight_records_unreachable_server_clearly(monkeypatch, tmp_path):
    import scripts.benchmark_vlalight_jev as benchmark
    from jevlight.jev_client import JevClient, JevResult
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    monkeypatch.setattr(JevClient, "evaluate", lambda *a, **kw: JevResult(
        error="ConnectionError: Max retries exceeded (localized OS error)"))
    assert benchmark.check_open_image_model(
        tmp_path, "Cloudflare/clef-flash", "http://127.0.0.1:30000", retries=0)
    record = json.loads((tmp_path / "preflight_clef-flash.json").read_text())
    assert record["status"] == "blocked_local_model"
    assert record["error"] == "Could not connect to the local model server at http://127.0.0.1:30000."


def test_open_vision_method_uses_same_vlalight_runner_and_separate_output(monkeypatch, tmp_path):
    import scripts.benchmark_vlalight_jev as benchmark
    case = build_cases()[0]
    commands = []
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    monkeypatch.setattr(benchmark, "build_cases", lambda: [case])
    monkeypatch.setattr(benchmark, "check_open_image_model", lambda *a, **kw: None)
    monkeypatch.setattr(benchmark.subprocess, "run", lambda command, **kw: (
        commands.append(command) or SimpleNamespace(returncode=1)
    ))
    output = tmp_path / "output"
    monkeypatch.setattr("sys.argv", ["benchmark", "--method", "d3-turbo", "--execute",
                                     "--seeds", "1", "--output", str(output),
                                     "--jev_base_url", "http://gpu-host:30000"])
    with pytest.raises(SystemExit) as error:
        benchmark.main()
    assert error.value.code == 1
    command = commands[0]
    assert command[1] == "run_jevlight.py"
    assert "--jev_transport" in command and command[command.index("--jev_transport") + 1] == "local"
    assert "--image_decisions" in command
    assert command[command.index("--jev_model") + 1] == "vllm-sr/d3-turbo"
    assert command[command.index("--jev_base_url") + 1] == "http://gpu-host:30000"
    result = json.loads((output / "d3-turbo.json").read_text())
    assert result["plan"]["method"] == "d3-turbo"
    assert result["plan"]["model"] == "vllm-sr/d3-turbo"
    assert result["runs"][0]["status"] == "failed"


def test_report_reads_open_model_two_stage_plan_without_official_result(tmp_path):
    from scripts.report_vlalight_jev import write_report
    plan = {"method": "d3-turbo", "cases": [build_cases()[0]], "seeds": [1]}
    (tmp_path / "plan_d3-turbo-vlalight.json").write_text(json.dumps(plan))
    write_report(tmp_path, "vlalight")
    report = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "plan_d3-turbo-vlalight.json" in report
    assert "d3-turbo v1.1" in report


def test_atomic_result_write_keeps_previous_result_on_replace_failure(monkeypatch, tmp_path):
    from pathlib import Path
    from scripts.benchmark_vlalight_jev import save_json
    path = tmp_path / "result.json"
    save_json(path, {"complete": 2})

    def fail_replace(*args):
        raise OSError("interrupted replacement")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        save_json(path, {"complete": 3})
    assert json.loads(path.read_text()) == {"complete": 2}


def test_resume_skips_corrupted_latest_summary_and_reuses_valid_seed(monkeypatch, tmp_path):
    import os
    import scripts.benchmark_vlalight_jev as benchmark
    case = build_cases()[0]
    directory = tmp_path / "records/VLALightBenchmark/maxpressure" / case["id"] / "seed_1"
    old, latest = directory / "old/summary.json", directory / "latest/summary.json"
    old.parent.mkdir(parents=True)
    latest.parent.mkdir()
    summary = {**valid_image_summary(case), "dry_run": True,
               "agent_mode": "maxpressure", "image_decisions": False}
    for field in ("avg_travel_time", "avg_waiting_time", "avg_queue_len",
                  "arrived_vehicle_count", "running_vehicle_count", "pending_vehicle_count"):
        summary[f"final/{field}"] = 1
    old.write_text(json.dumps(summary))
    latest.write_text('{"interrupted":')
    os.utime(old, (1, 1))
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    monkeypatch.setattr(benchmark, "build_cases", lambda: [case])
    monkeypatch.setattr(benchmark.subprocess, "run", lambda *a, **kw: pytest.fail("valid seed was rerun"))
    output = tmp_path / "output"
    monkeypatch.setattr("sys.argv", ["benchmark", "--method", "maxpressure", "--execute", "--resume",
                                     "--seeds", "1", "--output", str(output)])
    benchmark.main()
    result = json.loads((output / "maxpressure.json").read_text())
    assert result["runs"][0]["status"] == "complete"
    assert result["runs"][0]["summary_path"] == str(old.relative_to(tmp_path))
