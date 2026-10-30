from io import BytesIO
import json
from urllib.error import URLError

import pytest

from scripts import vision_server_network as network


@pytest.fixture
def hub(monkeypatch, tmp_path):
    monkeypatch.setattr(network, "ROOT", tmp_path)
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/vision_models.json").write_text(json.dumps(
        {"wemm-jev": {"model_id": "Rover00/WeMM-JEV", "revision": "a" * 40}}))


def test_only_checks_pinned_metadata_and_respects_endpoint(monkeypatch, hub):
    monkeypatch.setenv("HF_ENDPOINT", "https://hub.example.test/")
    calls = []

    def open_url(request, timeout):
        calls.append((request.full_url, timeout))
        return BytesIO(json.dumps({"sha": "a" * 40}).encode())

    monkeypatch.setattr(network, "urlopen", open_url)
    network.check(["wemm-jev"])
    assert calls == [("https://hub.example.test/api/models/Rover00/WeMM-JEV/revision/" + "a" * 40, 20)]


def test_no_route_exits_with_actionable_message(monkeypatch, hub):
    def unavailable(*a, **kw):
        raise URLError(OSError(101, "Network is unreachable"))

    monkeypatch.setattr(network, "urlopen", unavailable)
    with pytest.raises(SystemExit, match="network/proxy configuration"):
        network.check(["wemm-jev"])


def test_wrong_pinned_revision_is_rejected(monkeypatch, hub):
    monkeypatch.setattr(network, "urlopen", lambda *a, **kw: BytesIO(b'{"sha":"wrong"}'))
    with pytest.raises(SystemExit, match="metadata check failed"):
        network.check(["wemm-jev"])


def test_credentials_in_endpoint_are_not_printed_or_used(monkeypatch, hub):
    monkeypatch.setenv("HF_ENDPOINT", "https://user:secret@hub.example.test")
    monkeypatch.setattr(network, "urlopen", lambda *a, **kw: pytest.fail("Invalid endpoint used"))
    with pytest.raises(SystemExit, match="without credentials") as error:
        network.check(["wemm-jev"])
    assert "secret" not in str(error.value)
