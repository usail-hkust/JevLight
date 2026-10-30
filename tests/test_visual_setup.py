from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import fetch_vlalight_renderer as renderer


ROOT = Path(__file__).resolve().parents[1]


def test_renderer_fetch_uses_public_pinned_api_and_verifies_files(monkeypatch, tmp_path):
    name = "VLALight/TransSimHub/examples/Jinan/3d_assets/map.glb"
    data = b"fixture renderer asset"
    entries = [{"type": "blob", "path": name, "sha": renderer.blob_hash(data)}]
    requests = []

    def open_url(request, timeout):
        url = request if isinstance(request, str) else request.full_url
        requests.append(url)
        return BytesIO(json.dumps({"tree": entries}).encode() if "api.github.com" in url else data)

    monkeypatch.setattr(renderer.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(sys, "argv", ["fetch", "--destination", str(tmp_path)])
    renderer.main()
    renderer.main()
    assert (tmp_path / name).read_bytes() == data
    manifest = json.loads((tmp_path / "renderer-manifest.json").read_text())
    assert manifest["revision"] == renderer.REVISION
    assert len(requests) == 3  # A second verification reuses the validated asset.
    assert all(renderer.REVISION in url for url in requests)


def bash_path():
    git_bash = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    bash = str(git_bash) if os.name == "nt" and git_bash.is_file() else shutil.which("bash")
    if not bash:
        pytest.skip("Bash is not installed")
    return bash


def test_shared_output_lease_rejects_duplicate_and_releases_after_exit(tmp_path):
    from jevlight.simulation_checkpoint import OutputLease
    with OutputLease(tmp_path):
        with pytest.raises(RuntimeError, match="already owned"):
            with OutputLease(tmp_path):
                pytest.fail("Duplicate writer entered")
    with OutputLease(tmp_path):
        pass


def test_clean_setup_installs_runner_and_fetches_assets_without_models(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(ROOT / "scripts/setup_vision_runner.sh", scripts / "setup_vision_runner.sh")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    runner_bin = tmp_path / ".local/vision-runner/bin"
    runner_bin.mkdir(parents=True)
    calls = tmp_path / "calls.txt"
    commands = {
        binaries / "python3": '#!/usr/bin/env bash\nexit 0\n',
        binaries / "xvfb-run": '#!/usr/bin/env bash\nexit 0\n',
        binaries / "uv": '#!/usr/bin/env bash\nprintf "uv %s\\n" "$*" >> "$SETUP_CALLS"\n',
        runner_bin / "sumo": '#!/usr/bin/env bash\nprintf "sumo %s\\n" "$*" >> "$SETUP_CALLS"\n',
        runner_bin / "python": '#!/usr/bin/env bash\nprintf "runner %s\\n" "$*" >> "$SETUP_CALLS"\n',
    }
    for path, content in commands.items():
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
    subprocess.run([bash_path(), str(scripts / "setup_vision_runner.sh")], check=True,
        env={**os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
             "SETUP_CALLS": str(calls)}, text=True, capture_output=True)
    lines = calls.read_text().splitlines()
    assert len(lines) == 3
    assert "-r scripts/vision_runner_requirements.txt" in lines[0]
    assert lines[1:] == ["sumo --version", "runner scripts/fetch_vlalight_renderer.py"]
