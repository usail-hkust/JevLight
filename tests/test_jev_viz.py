"""Unit tests for the 3D visualizer server core (no network beyond loopback,
no SUMO binary: the runtimes use a fake traci connection, the network model
reads the real Jinan net file via sumolib)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import requests

from jevlight import viz_server

REPO_ROOT = Path(__file__).resolve().parents[1]
NET_PATH = REPO_ROOT / "data" / "Jinan" / "3_4" / "roadnet_3_4.net.xml"


class FakeVehicleDomain:
    def __init__(self):
        self.subscriptions = {}

    def getIDList(self):
        return ["v1", "v2"]

    def subscribe(self, vid, variables):
        self.subscriptions[vid] = variables

    def getAllSubscriptionResults(self):
        return {
            "v1": {
                viz_server.VAR_POSITION3D: (410.0, 820.0, 0.0),
                viz_server.VAR_ANGLE: 90.0,
                viz_server.VAR_SPEED: 5.0,
                viz_server.VAR_COLOR: (255, 0, 0, 255),
                viz_server.VAR_VEHICLECLASS: "passenger",
            },
            "v2": {
                viz_server.VAR_POSITION3D: (430.0, 850.0, 0.0),
                viz_server.VAR_ANGLE: 0.0,
                viz_server.VAR_SPEED: 0.0,
                viz_server.VAR_COLOR: (0, 200, 255, 255),
                viz_server.VAR_VEHICLECLASS: "bus",
            },
        }


class FakeTrafficlightDomain:
    def getIDList(self):
        return ["t0"]

    def getRedYellowGreenState(self, tls_id):
        return "rrGG"


class FakeSimulationDomain:
    def __init__(self):
        self.time = 0.0

    def getTime(self):
        return self.time

    def getDeltaT(self):
        return 0.01  # tiny: tests step as fast as they like


class FakeConn:
    def __init__(self):
        self.simulation = FakeSimulationDomain()
        self.vehicle = FakeVehicleDomain()
        self.trafficlight = FakeTrafficlightDomain()
        self.steps = 0
        self.closed = False

    def simulationStep(self):
        self.steps += 1
        self.simulation.time += 0.01

    def close(self):
        self.closed = True


def start_runtime(conn, **kwargs):
    runtime = viz_server.SumoRuntime(conn, playing=False, **kwargs)
    thread = threading.Thread(target=runtime.run, daemon=True)
    thread.start()
    return runtime, thread


def wait_for(predicate, timeout=5.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TestNetworkModel:
    def test_loads_jinan_network(self):
        model = viz_server.NetworkModel.load(str(NET_PATH))
        payload = model.payload
        assert len(payload["lanes"]) >= 100
        assert len(payload["tls"]) == 12
        assert payload["offset"] == [400.0, 800.0]
        first = payload["lanes"][0]
        assert first["width"] > 0
        assert len(first["shape"]) >= 2
        for x, y in first["shape"]:
            assert -1e6 < x < 1e6 and -1e6 < y < 1e6
        tls_ids = {entry["id"] for entry in payload["tls"]}
        assert len(tls_ids) == 12


class TestVehicleClassMapping:
    def test_class_index_mapping(self):
        f = viz_server.vehicle_class_index
        assert f("passenger") == 0
        assert f("Bus") == 1
        assert f("truck") == 1
        assert f("delivery") == 1
        assert f("bicycle") == 2
        assert f("motorcycle") == 2
        assert f(None) == 0
        assert f("") == 0

    def test_vehicle_rows_carry_class_index(self):
        frame = viz_server.capture_frame(FakeConn(), (400.0, 800.0))
        by_id = {row[0]: row for row in frame["vehicles"]}
        assert by_id["v1"][9] == 0  # passenger -> car
        assert by_id["v2"][9] == 1  # bus -> long vehicle


class TestSumoRuntime:
    def test_step_command_publishes_offset_frames(self):
        conn = FakeConn()
        runtime, thread = start_runtime(conn, offset=(400.0, 800.0))
        try:
            assert conn.steps == 0  # paused: nothing steps on its own
            runtime.command(action="step")
            assert wait_for(lambda: conn.steps == 1)
            assert wait_for(lambda: runtime.frame["seq"] == 1)

            frame = runtime.frame
            by_id = {row[0]: row for row in frame["vehicles"]}
            # Vehicle positions are shifted into network coordinates.
            assert by_id["v1"][1:3] == [10.0, 20.0]
            assert by_id["v1"][4] == 90.0  # angle
            assert by_id["v1"][5] == 5.0  # speed
            assert by_id["v1"][6:9] == [255, 0, 0]
            assert frame["tls"] == {"t0": "rrGG"}
            assert frame["t"] > 0
        finally:
            runtime.close()
            thread.join(timeout=5)
        assert conn.closed

    def test_pause_play_and_speed(self):
        conn = FakeConn()
        runtime, thread = start_runtime(conn)
        try:
            runtime.command(action="play", speed=50.0)
            runtime.command(action="speed", speed=100.0)
            assert wait_for(lambda: conn.steps >= 3)
            runtime.command(action="pause")
            steps_at_pause = conn.steps
            time.sleep(0.2)
            assert conn.steps == steps_at_pause
            assert runtime.playing is False
        finally:
            runtime.close()
            thread.join(timeout=5)

    def test_max_steps_stops_stepping(self):
        conn = FakeConn()
        runtime, thread = start_runtime(conn, max_steps=2)
        try:
            runtime.command(action="play")
            assert wait_for(lambda: conn.steps >= 2)
            time.sleep(0.2)
            assert conn.steps == 2
            assert runtime.playing is False
        finally:
            runtime.close()
            thread.join(timeout=5)


class TestPassiveRuntime:
    def test_publish_uses_host_connection_and_offsets(self):
        conn = FakeConn()
        runtime = viz_server.PassiveRuntime(offset=(400.0, 800.0))
        conn.simulationStep()  # the host (not the runtime) steps SUMO
        runtime.publish(conn)
        frame = runtime.frame
        assert frame["seq"] == 1
        by_id = {row[0]: row for row in frame["vehicles"]}
        assert by_id["v1"][1:3] == [10.0, 20.0]
        assert frame["tls"] == {"t0": "rrGG"}
        conn.simulationStep()
        runtime.publish(conn)
        assert runtime.frame["seq"] == 2

    def test_pause_blocks_host_until_play(self):
        runtime = viz_server.PassiveRuntime()
        runtime.command(action="pause")
        released = threading.Event()

        def host_loop():
            runtime.wait_until_running(poll=0.05)
            released.set()

        thread = threading.Thread(target=host_loop, daemon=True)
        thread.start()
        time.sleep(0.3)
        assert not released.is_set()  # the experiment loop is gated
        runtime.command(action="play")
        assert released.wait(timeout=2)

    def test_single_step_releases_once_while_paused(self):
        runtime = viz_server.PassiveRuntime()
        runtime.command(action="pause")
        runtime.command(action="step")
        runtime.wait_until_running(poll=0.05)  # consumes the step request
        released = threading.Event()
        threading.Thread(
            target=lambda: (
                runtime.wait_until_running(poll=0.05),
                released.set(),
            ),
            daemon=True,
        ).start()
        time.sleep(0.3)
        assert not released.is_set()  # no pending step: gated again
        runtime.close()
        assert released.wait(timeout=2)  # close releases the host loop

    def test_commands_via_http_endpoint(self):
        runtime = viz_server.PassiveRuntime(offset=(400.0, 800.0))
        network = viz_server.NetworkModel.load(str(NET_PATH))
        server = viz_server.make_viz_server(
            runtime,
            network.payload,
            viz_dir=REPO_ROOT / "viz",
            host="127.0.0.1",
            port=0,
        )
        http_thread = threading.Thread(target=server.serve_forever, daemon=True)
        http_thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            requests.post(
                f"{base}/api/command", json={"action": "pause"}, timeout=5
            ).raise_for_status()
            assert wait_for(lambda: runtime.paused)
            released = threading.Event()
            threading.Thread(
                target=lambda: (
                    runtime.wait_until_running(poll=0.05),
                    released.set(),
                ),
                daemon=True,
            ).start()
            time.sleep(0.3)
            assert not released.is_set()
            requests.post(
                f"{base}/api/command", json={"action": "step"}, timeout=5
            ).raise_for_status()
            assert released.wait(timeout=2)
        finally:
            runtime.close()
            server.shutdown()
            server.server_close()


def read_sse_until(host, port, want_event, timeout=5.0):
    """Minimal SSE reader over a raw socket.

    requests' iter_lines buffers unbounded HTTP/1.0 streams and stalls on
    small reads; the browser EventSource (the real consumer) is unaffected,
    so the test reads the socket directly.
    """
    import socket

    sock = socket.create_connection((host, port), timeout=timeout)
    sock.sendall(
        f"GET /api/stream HTTP/1.1\r\nHost: {host}\r\n"
        "Accept: text/event-stream\r\n\r\n".encode()
    )
    sock.settimeout(timeout)
    data = b""
    events = []
    saw_header = False
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            if not saw_header:
                _header, sep, rest = data.partition(b"\r\n\r\n")
                if not sep:
                    continue  # response headers not complete yet
                data = rest
                saw_header = True
            while b"\n\n" in data:
                block, _, data = data.partition(b"\n\n")
                name = None
                payload = None
                for line in block.decode("utf-8").splitlines():
                    if line.startswith("event:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        payload = json.loads(line.split(":", 1)[1])
                if name is not None:
                    events.append((name, payload))
                if name == want_event:
                    return events
    except socket.timeout:
        pass
    finally:
        sock.close()
    return events


class TestVizHttp:
    def make_server(self):
        conn = FakeConn()
        runtime, thread = start_runtime(conn, offset=(400.0, 800.0))
        network = viz_server.NetworkModel.load(str(NET_PATH))
        server = viz_server.make_viz_server(
            runtime,
            network.payload,
            viz_dir=REPO_ROOT / "viz",
            host="127.0.0.1",
            port=0,
        )
        http_thread = threading.Thread(target=server.serve_forever, daemon=True)
        http_thread.start()
        return runtime, thread, server, f"http://127.0.0.1:{server.server_address[1]}"

    def stop(self, runtime, thread, server):
        runtime.close()
        thread.join(timeout=5)
        server.shutdown()
        server.server_close()

    def test_static_frontend_and_network(self):
        runtime, thread, server, base = self.make_server()
        try:
            index = requests.get(f"{base}/", timeout=5)
            assert index.status_code == 200
            assert "JevLight" in index.text
            app = requests.get(f"{base}/js/app.js", timeout=5)
            assert app.status_code == 200
            assert "trafficlight" not in app.text or "updateTrafficLights" in app.text
            network = requests.get(f"{base}/api/network", timeout=5).json()
            assert len(network["lanes"]) >= 100
            missing = requests.get(f"{base}/nope", timeout=5)
            assert missing.status_code == 404
        finally:
            self.stop(runtime, thread, server)

    def test_path_traversal_rejected(self):
        runtime, thread, server, base = self.make_server()
        try:
            attack = requests.get(
                f"{base}/js/../../jevlight/config.py", timeout=5
            )
            assert attack.status_code in (403, 404)
            assert "DIC_PATH" not in attack.text
        finally:
            self.stop(runtime, thread, server)

    def test_command_endpoint_controls_runtime(self):
        runtime, thread, server, base = self.make_server()
        try:
            bad = requests.post(
                f"{base}/api/command", json={"action": "warp"}, timeout=5
            )
            assert bad.status_code == 400
            ok = requests.post(
                f"{base}/api/command", json={"action": "play"}, timeout=5
            )
            assert ok.status_code == 200
            assert wait_for(lambda: runtime.playing)
            requests.post(
                f"{base}/api/command", json={"action": "pause"}, timeout=5
            )
            assert wait_for(lambda: not runtime.playing)
        finally:
            self.stop(runtime, thread, server)

    def test_stream_sends_init_then_frames(self):
        runtime, thread, server, base = self.make_server()
        try:
            runtime.command(action="step")
            host = "127.0.0.1"
            port = server.server_address[1]
            events = read_sse_until(host, port, want_event="frame")
            kinds = [name for name, _ in events]
            assert kinds[0] == "init"
            assert "frame" in kinds
            init = dict(events)["init"]
            assert init["offset"] == [400.0, 800.0]
            assert "lanes" in init and "step_length" in init
            frame = [payload for name, payload in events if name == "frame"][0]
            assert frame["tls"] == {"t0": "rrGG"}
            assert any(row[0] == "v1" for row in frame["vehicles"])
        finally:
            self.stop(runtime, thread, server)
