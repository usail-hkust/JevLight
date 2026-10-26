"""Download and pin StartLux-Decision Instant snapshots for the 4A800 queue.

The 4A800 container cannot reach huggingface.co directly; run with
``HF_ENDPOINT=https://hf-mirror.com``. A snapshot is written as a manifest that
``acceptance_identity`` and the queue use to prove completeness before a model
is scheduled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "scripts/model_downloads/models.json"
SCOPE = ROOT / "config/decision_models/startlux_scope.json"
MODELS = ROOT / ".local/models"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def files(weights: Path) -> list[dict]:
    entries = []
    for path in sorted(weights.rglob("*")):
        if not path.is_file() or ".cache" in path.parts:
            continue
        entries.append({"path": str(path.relative_to(weights)),
                        "size": path.stat().st_size, "sha256": sha256(path)})
    return entries


def manifest(weights: Path, repo: str, revision: str) -> dict:
    return {
        "model_id": repo,
        "revision": revision,
        "status": "downloaded",
        "weights_path": str(weights.relative_to(ROOT)),
        "bases": [],
        "files": files(weights),
    }


def complete(weights: Path, repo: str, revision: str) -> bool:
    path = weights.parent / "manifest.json"
    if not path.is_file() or not (weights / "config.json").is_file():
        return False
    try:
        current = json.loads(path.read_text())
    except ValueError:
        return False
    if (current.get("status") != "downloaded" or current.get("revision") != revision
            or current.get("model_id") != repo):
        return False
    for entry in current.get("files", []):
        target = weights / entry["path"]
        if not target.is_file() or target.stat().st_size != entry["size"]:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keys", nargs="*", help="catalog keys; default: the StartLux scope")
    parser.add_argument("--check", action="store_true", help="verify only, download nothing")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    keys = args.keys or json.loads(SCOPE.read_text())
    catalog = json.loads(CATALOG.read_text())
    pending = []
    for key in keys:
        if key not in catalog:
            raise SystemExit(f"{key}: not in {CATALOG}")
        repo, revision = catalog[key]["model_id"], catalog[key]["revision"]
        weights = MODELS / key / "weights"
        if complete(weights, repo, revision):
            print(json.dumps({"key": key, "status": "ready", "weights": str(weights)}), flush=True)
            continue
        if args.check:
            print(json.dumps({"key": key, "status": "missing", "weights": str(weights)}), flush=True)
            continue
        pending.append((key, repo, revision, weights))
    for key, repo, revision, weights in pending:
        print(json.dumps({"key": key, "status": "downloading", "repo": repo,
                          "revision": revision}), flush=True)
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=repo, revision=revision, local_dir=weights,
                          max_workers=args.workers)
        weights.mkdir(parents=True, exist_ok=True)
        value = manifest(weights, repo, revision)
        target = weights.parent / "manifest.json"
        pending_path = target.with_suffix(".json.tmp")
        pending_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        pending_path.replace(target)
        print(json.dumps({"key": key, "status": "ready", "files": len(value["files"]),
                          "bytes": sum(entry["size"] for entry in value["files"])}), flush=True)


if __name__ == "__main__":
    main()
