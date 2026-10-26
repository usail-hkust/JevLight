"""Download StartLux snapshots with one resumable curl per file.

The domestic mirror throttles many ranged connections to one file, but serves
separate files in parallel. Large folders (27B has 11 shards) therefore gain
from running a few single-connection curls at once.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.model_downloads.startlux_snapshots import ROOT, complete, manifest

CATALOG = ROOT / "scripts/model_downloads/models.json"
SCOPE = ROOT / "config/decision_models/startlux_scope.json"
MODELS = ROOT / ".local/models"
ENDPOINT = os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com").rstrip("/")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
PRINT = threading.Lock()


def repository_files(repo: str, revision: str) -> list[str]:
    import urllib.request
    request = urllib.request.Request(
        f"{ENDPOINT}/api/models/{repo}/revision/{revision}",
        headers={"User-Agent": "huggingface_hub/0.36.2"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read())
    return [entry["rfilename"] for entry in payload.get("siblings", [])]


def fetch(name: str, repo: str, revision: str, weights: Path) -> str:
    url = f"{ENDPOINT}/{repo}/resolve/{revision}/{name}"
    target = weights / name
    target.parent.mkdir(parents=True, exist_ok=True)
    command = ["curl", "-L", "--fail", "--retry", "5", "--retry-delay", "2",
               "-C", "-", "-o", str(target), url]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode not in (0, 33, 36):
        raise RuntimeError(f"{name}: curl {result.returncode}: {result.stderr[-500:]}")
    with PRINT:
        print(f"  {name}: {target.stat().st_size / 1e9:.2f} GB", flush=True)
    return name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keys", nargs="*", help="default: the StartLux scope")
    parser.add_argument("--files", type=int, default=4, help="parallel files")
    args = parser.parse_args()
    keys = args.keys or json.loads(SCOPE.read_text())
    catalog = json.loads(CATALOG.read_text())
    for key in keys:
        entry = catalog[key]
        repo, revision = entry["model_id"], entry["revision"]
        weights = MODELS / key / "weights"
        if complete(weights, repo, revision):
            print(json.dumps({"key": key, "status": "ready"}), flush=True)
            continue
        print(json.dumps({"key": key, "status": "downloading", "repo": repo}), flush=True)
        names = repository_files(repo, revision)
        with ThreadPoolExecutor(max_workers=args.files) as pool:
            list(pool.map(lambda name: fetch(name, repo, revision, weights), names))
        value = manifest(weights, repo, revision)
        destination = weights.parent / "manifest.json"
        pending = destination.with_suffix(".json.tmp")
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        pending.replace(destination)
        print(json.dumps({"key": key, "status": "ready",
                          "bytes": sum(item["size"] for item in value["files"])}), flush=True)


if __name__ == "__main__":
    main()
