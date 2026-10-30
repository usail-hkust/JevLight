import json
from pathlib import Path
import sys

import pytest

from scripts import check_wemm_cuda


ROOT = Path(__file__).resolve().parents[1]


def test_cuda_check_writes_evidence_only_after_success(monkeypatch, tmp_path):
    output = tmp_path / "checks/ready.json"
    monkeypatch.setattr(sys, "argv", ["check_wemm_cuda", "--output", str(output)])
    monkeypatch.setattr(check_wemm_cuda, "check", lambda: {"status": "ready", "torch": "fixture"})
    check_wemm_cuda.main()
    assert json.loads(output.read_text()) == {"status": "ready", "torch": "fixture"}


def test_cuda_failure_does_not_create_ready_record(monkeypatch, tmp_path):
    output = tmp_path / "ready.json"
    monkeypatch.setattr(sys, "argv", ["check_wemm_cuda", "--output", str(output)])

    def fail():
        raise RuntimeError("incompatible CUDA kernel")

    monkeypatch.setattr(check_wemm_cuda, "check", fail)
    with pytest.raises(RuntimeError, match="incompatible"):
        check_wemm_cuda.main()
    assert not output.exists()


def test_regular_we_mm_setup_installs_and_checks_the_exact_optional_kernel():
    source = (ROOT / "scripts/run_vision_server.sh").read_text(encoding="utf-8")
    assert "if ! \"$PY\" -c 'import causal_conv1d'" in source
    assert "causal_conv1d-1.7.0+cu12torch2.8cxx11abiTRUE-cp312-cp312-linux_x86_64.whl" in source
    assert source.index("scripts/check_wemm_cuda.py") < source.index('"$PY" scripts/serve_vision_model.py')
