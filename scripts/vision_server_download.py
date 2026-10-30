"""Use the same pinned Hub snapshots while exposing local download growth."""
import argparse
import json
from pathlib import Path
import shutil
from threading import Event, Thread

ROOT = Path(__file__).resolve().parents[1]


def folder_bytes(folder):
    total = 0
    for path in folder.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            pass  # Hub workers rename completed partial files while we scan.
    return total


def download(key, folder, stage):
    from huggingface_hub import snapshot_download

    spec = json.loads((ROOT / "config/vision_models.json").read_text(encoding="utf-8"))[key]
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stopped = Event()

    def progress():
        while not stopped.wait(15):
            print(f"[DOWNLOAD] {key}: local files including partials "
                  f"{folder_bytes(folder) / 1024**3:.2f} GiB; "
                  f"disk free {shutil.disk_usage(folder).free / 1024**3:.2f} GiB", flush=True)

    worker = Thread(target=progress, daemon=True)
    worker.start()
    print(f"[DOWNLOAD] {key}: starting {stage}, pinned revision {spec['revision']}", flush=True)
    kwargs = {}
    if stage == "sources":
        kwargs["allow_patterns"] = ['*.py', '*.json', '*.txt', '*.md', '*.jinja', 'LICENSE*']
    try:
        snapshot_download(spec['model_id'], revision=spec['revision'], local_dir=str(folder), **kwargs)
        if stage == "full":
            (folder / "jevlight-download.json").write_text(json.dumps(
                {name: spec[name] for name in ("model_id", "revision")}), encoding="utf-8")
    finally:
        stopped.set()
        worker.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key")
    parser.add_argument("folder", type=Path)
    parser.add_argument("stage", choices=("sources", "full"))
    args = parser.parse_args()
    download(args.key, args.folder, args.stage)
