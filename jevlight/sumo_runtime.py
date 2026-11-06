"""Select and validate the SUMO runtime used by every simulation process."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REQUIRED_VERSION = (1, 28, 0)


def resolve_sumo_binary() -> str:
    configured = os.environ.get("SUMO_BINARY")
    if configured:
        return configured
    python_dir = Path(sys.executable).resolve().parent
    candidates = [python_dir / "sumo.exe", python_dir / "sumo",
                  python_dir.parent / "bin" / "sumo.exe", python_dir.parent / "bin" / "sumo"]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("sumo") or "sumo"


def sumo_version(binary: str | None = None) -> tuple[int, int, int]:
    output = subprocess.run([binary or resolve_sumo_binary(), "--version"],
                            capture_output=True, text=True, timeout=15)
    if output.returncode:
        raise RuntimeError(f"SUMO runtime preflight exited {output.returncode}: "
                           f"{output.stdout}\n{output.stderr}")
    match = re.search(r"SUMO(?:\s+sumo)?\s+(?:Version\s+)?(\d+)\.(\d+)\.(\d+)", output.stdout)
    if not match:
        raise RuntimeError("Could not determine SUMO version")
    return tuple(map(int, match.groups()))


def require_sumo_128(binary: str | None = None) -> str:
    selected = binary or resolve_sumo_binary()
    version = sumo_version(selected)
    if version != REQUIRED_VERSION:
        raise RuntimeError(f"SUMO 1.28.0 is required; selected {selected} reports {version}")
    return selected
