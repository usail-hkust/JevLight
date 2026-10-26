"""Resumable multi-connection downloader for StartLux snapshots.

The 4A800 container reaches the HF mirror but a single transfer is ~5 MB/s.
This tool reads sizes from the mirror's CDN (Range/HEAD), downloads each file
with 16 ranged connections, verifies every byte locally by SHA-256 and then
writes the same manifest as ``startlux_snapshots``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.model_downloads.startlux_snapshots import ROOT, complete, manifest

CATALOG = ROOT / "scripts/model_downloads/models.json"
SCOPE = ROOT / "config/decision_models/startlux_scope.json"
MODELS = ROOT / ".local/models"
ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com").rstrip("/")
os.environ.setdefault("HF_ENDPOINT", ENDPOINT)
CHUNK = 32 << 20
CONNECTIONS = 16
USER_AGENT = "huggingface_hub/0.36.2"


def _request(url: str, *, method="GET", headers=None, timeout=120):
    merged = {"User-Agent": USER_AGENT}
    merged.update(headers or {})
    request = urllib.request.Request(url, method=method, headers=merged)
    return urllib.request.urlopen(request, timeout=timeout)


def file_size(url: str) -> int:
    try:
        with _request(url, headers={"Range": "bytes=0-0"}) as response:
            content_range = response.headers.get("Content-Range", "")
            if "/" in content_range:
                return int(content_range.rsplit("/", 1)[1])
            length = response.headers.get("Content-Length")
            if length:
                return int(length)
    except urllib.error.HTTPError:
        pass
    with _request(url, method="HEAD") as response:
        length = response.headers.get("Content-Length")
        return int(length) if length else None


def repository_files(repo: str, revision: str) -> list[str]:
    url = f"{ENDPOINT}/api/models/{repo}/revision/{revision}"
    with _request(url) as response:
        payload = json.loads(response.read())
    return [entry["rfilename"] for entry in payload.get("siblings", [])]


def download_one(url: str, target: Path, size: int | None) -> None:
    part = target.with_name(target.name + ".part")
    part.parent.mkdir(parents=True, exist_ok=True)
    if size is None or size < (1 << 20):
        with _request(url, timeout=3600) as response, part.open("wb") as stream:
            shutil.copyfileobj(response, stream, 4 << 20)
        if size is not None and part.stat().st_size != size:
            raise RuntimeError(f"{target.name}: streamed {part.stat().st_size} bytes, expected {size}")
        part.replace(target)
        print(f"  {target.name}: complete (streamed)", flush=True)
        return
    if part.exists() and part.stat().st_size != size:
        part.unlink()
    descriptor = os.open(part, os.O_RDWR | os.O_CREAT, 0o644)
    started = time.monotonic()
    try:
        os.ftruncate(descriptor, size)
        chunks = [(start, min(start + CHUNK, size) - 1) for start in range(0, size, CHUNK)]
        done = [0]
        lock = threading.Lock()

        def fetch(bounds):
            start, end = bounds
            last = None
            for attempt in range(8):
                try:
                    with _request(url, headers={"Range": f"bytes={start}-{end}"}, timeout=600) as response:
                        if response.status != 206:
                            raise RuntimeError(f"range request returned {response.status}")
                        payload = response.read()
                    if len(payload) != end - start + 1:
                        raise RuntimeError(f"short range {len(payload)} != {end - start + 1}")
                    os.pwrite(descriptor, payload, start)
                    with lock:
                        before = done[0]
                        done[0] += len(payload)
                        if done[0] // (2 << 30) != before // (2 << 30):
                            rate = done[0] / max(0.001, time.monotonic() - started) / 1e6
                            print(f"  {target.name}: {done[0] / 1e9:.1f}/{size / 1e9:.1f} GB at {rate:.1f} MB/s",
                                  flush=True)
                    return
                except Exception as error:  # noqa: BLE001 - retry transport errors
                    last = error
                    wait = 30 if getattr(error, "code", None) == 429 else 2 * (attempt + 1)
                    time.sleep(wait)
            raise RuntimeError(f"range {start}-{end} failed: {last}")

        with ThreadPoolExecutor(max_workers=CONNECTIONS) as pool:
            list(pool.map(fetch, chunks))
    finally:
        os.close(descriptor)
    part.replace(target)
    print(f"  {target.name}: complete in {time.monotonic() - started:.0f}s", flush=True)


def main() -> None:
    global CONNECTIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keys", nargs="*", help="default: the StartLux scope")
    parser.add_argument("--connections", type=int, default=CONNECTIONS)
    args = parser.parse_args()
    keys = args.keys or json.loads(SCOPE.read_text())
    CONNECTIONS = args.connections
    catalog = json.loads(CATALOG.read_text())
    for key in keys:
        entry = catalog[key]
        repo, revision = entry["model_id"], entry["revision"]
        weights = MODELS / key / "weights"
        if complete(weights, repo, revision):
            print(json.dumps({"key": key, "status": "ready"}), flush=True)
            continue
        print(json.dumps({"key": key, "status": "downloading", "repo": repo}), flush=True)
        small = []
        for name in repository_files(repo, revision):
            url = f"{ENDPOINT}/{repo}/resolve/{revision}/{name}"
            target = weights / name
            target.parent.mkdir(parents=True, exist_ok=True)
            size = file_size(url)
            if size is None or size < (4 << 20):
                small.append(name)
                continue
            if target.is_file() and target.stat().st_size == size:
                continue
            print(f"  {name} ({size / 1e9:.2f} GB)", flush=True)
            download_one(url, target, size)
        if small:
            from huggingface_hub import snapshot_download
            print(f"  small files via hub: {len(small)}", flush=True)
            snapshot_download(repo_id=repo, revision=revision, local_dir=weights,
                              allow_patterns=small, max_workers=4)
        value = manifest(weights, repo, revision)
        destination = weights.parent / "manifest.json"
        pending = destination.with_suffix(".json.tmp")
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        pending.replace(destination)
        print(json.dumps({"key": key, "status": "ready",
                          "bytes": sum(item["size"] for item in value["files"])}), flush=True)


if __name__ == "__main__":
    main()
