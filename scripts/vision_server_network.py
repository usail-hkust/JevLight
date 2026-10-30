"""Check pinned Hub metadata without downloading weights or running inference."""
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def check(keys):
    models = json.loads((ROOT / "config/vision_models.json").read_text(encoding="utf-8"))
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise SystemExit("HF_ENDPOINT must be an HTTP(S) URL without credentials, query or fragment")
    for key in keys:
        if key not in models:
            raise SystemExit(f"Unknown model: {key}")
        spec = models[key]
        request = Request(f"{endpoint}/api/models/{spec['model_id']}/revision/{spec['revision']}",
                          headers={"User-Agent": "JevLight-vision-network-check"})
        try:
            with urlopen(request, timeout=20) as response:
                metadata = json.load(response)
            if not isinstance(metadata, dict) or metadata.get("sha") != spec["revision"]:
                raise ValueError("Hub returned a different revision")
        except (OSError, ValueError) as error:
            detail = f"HTTP {error.code}" if isinstance(error, HTTPError) else type(error).__name__
            raise SystemExit(
                f"Hugging Face metadata check failed for {key}: {detail}. No weights were downloaded. "
                "Check this machine's network/proxy configuration and rerun this check. "
                "An explicit HF_ENDPOINT is also supported. "
                "Metadata access does not guarantee access to weight-file download hosts.") from None
        print(f"Hub metadata reachable: {key}, pinned revision {spec['revision']}", flush=True)


if __name__ == "__main__":
    check(sys.argv[1:] or ["wemm-jev"])
