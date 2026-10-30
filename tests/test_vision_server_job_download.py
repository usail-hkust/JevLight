import json
import os
import sys
from types import SimpleNamespace

import pytest

from scripts import vision_server_download as download
from scripts import vision_server_job as job
from scripts.file_lock import lock_exclusive


def test_job_exec_inherits_lock_without_starting_another_process(monkeypatch, tmp_path):
    monkeypatch.setattr(job, "ROOT", tmp_path)
    calls = []

    def execute(binary, arguments, env):
        fd = int(env["JEVLIGHT_VISION_LOCK_FD"])
        assert os.get_inheritable(fd)
        calls.append((binary, arguments))

    monkeypatch.setattr(job.os, "execvpe", execute)
    job.launch(["--mode", "run", "--models", "wemm-jev"])
    assert calls == [("bash", ["bash", str(tmp_path / "scripts/run_vision_server.sh"), "--mode", "run", "--models", "wemm-jev"])]


def test_second_job_does_not_overwrite_owner_or_start(monkeypatch, tmp_path):
    monkeypatch.setattr(job, "ROOT", tmp_path)
    path = tmp_path / ".local/vision-server.lock"
    path.parent.mkdir()
    with path.open("a+b") as held:
        held.write(b"owner\n")
        held.flush()
        lock_exclusive(held, nonblocking=True)
        monkeypatch.setattr(job.os, "execvpe", lambda *a: pytest.fail("Duplicate job started"))
        with pytest.raises(SystemExit, match="already owns"):
            job.launch(["run"])
        held.seek(0)
        assert held.read() == b"owner\n"


@pytest.fixture
def catalog(monkeypatch, tmp_path):
    monkeypatch.setattr(download, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    spec = {"model_id": "test/model", "revision": "a" * 40}
    (tmp_path / "config/vision_models.json").write_text(json.dumps({"wemm-jev": spec}))
    return spec


def test_download_progress_counts_partial_files(tmp_path):
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache/part.incomplete").write_bytes(b"123")
    (tmp_path / "finished.bin").write_bytes(b"4567")
    assert download.folder_bytes(tmp_path) == 7


@pytest.mark.parametrize("stage", ["sources", "full"])
def test_download_keeps_pinned_snapshot_arguments(monkeypatch, tmp_path, catalog, stage):
    calls = []
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(
        snapshot_download=lambda *a, **kw: calls.append((a, kw))))
    folder = tmp_path / "weights"
    download.download("wemm-jev", folder, stage)
    args, kwargs = calls[0]
    assert args == (catalog["model_id"],)
    assert kwargs["revision"] == catalog["revision"] and kwargs["local_dir"] == str(folder)
    assert ("allow_patterns" in kwargs) == (stage == "sources")
    marker = folder / "jevlight-download.json"
    assert marker.exists() == (stage == "full")
    if marker.exists():
        assert json.loads(marker.read_text()) == catalog


def test_failed_download_preserves_partial_files_without_success_marker(monkeypatch, tmp_path, catalog):
    folder = tmp_path / "weights"

    def fail(*a, **kw):
        (folder / "part.incomplete").write_text("partial")
        raise ConnectionError("interrupted")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=fail))
    with pytest.raises(ConnectionError, match="interrupted"):
        download.download("wemm-jev", folder, "full")
    assert (folder / "part.incomplete").read_text() == "partial"
    assert not (folder / "jevlight-download.json").exists()
