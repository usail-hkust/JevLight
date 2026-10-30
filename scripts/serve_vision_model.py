"""Serve pinned author runtimes behind one loopback System One interface."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODELS = json.loads((ROOT / "config/vision_models.json").read_text(encoding="utf-8"))


def load_runtime(key, path):
    """Keep the model authors' prompts, decision heads and numerical paths."""
    spec = MODELS[key]
    if key == "wemm-jev":
        sys.path.insert(0, str(path))
        from inference import D3Engine
        engine = D3Engine(model=str(path), device="cuda:0", batch_size=1,
                          model_name=spec["model_id"], permutation_average=False)

        def evaluate(body):
            response, _ = engine(state=body["state"], questions=body["questions"], images=body.get("images"))
            return response

        return evaluate
    if key == "d3-turbo":
        from transformers import AutoModel
        model = AutoModel.from_pretrained(str(path), trust_remote_code=True,
                                          device="cuda:0", batch_size=1)
        return lambda body: model.system_one(state=body["state"], questions=body["questions"],
                                             images=body.get("images"))
    sys.path.insert(0, str(path / "serve"))
    from amos.serve import load_engine
    engine = load_engine(str(path), "cuda", spec["model_id"], 131072, 1,
                         strict=True, state_cache=False)
    return engine


def validate_request(body, model_id):
    if not isinstance(body, dict) or body.get("model") != model_id:
        raise ValueError("Request must select the loaded model explicitly")
    if "state" not in body or not isinstance(body.get("questions"), dict) or not body["questions"]:
        raise ValueError("state and nonempty questions are required")
    if len(body["questions"]) > 24:
        raise ValueError("This visual protocol supports at most 24 questions")
    for question in body["questions"].values():
        if (not isinstance(question, dict) or question.get("type") != "choice" or
                not isinstance(question.get("criteria"), dict) or not 2 <= len(question["criteria"]) <= 255):
            raise ValueError("Expected typed choice questions with 2 to 255 criteria")
    images = body.get("images", [])
    if not isinstance(images, list) or len(images) > 8:
        raise ValueError("Expected at most 8 camera images")
    if any(not isinstance(img, str) or not img.startswith(("data:image/png;base64,", "data:image/jpeg;base64,"))
           for img in images):
        raise ValueError("Only inline PNG/JPEG images are accepted")
    if set(body) - {"model", "state", "questions", "images"}:
        raise ValueError("Unsupported request fields")


def validate_response(response, questions):
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise ValueError("Author runtime returned no answers")
    for key, question in questions.items():
        answer = response["answers"].get(key)
        if (not isinstance(answer, dict) or answer.get("error") or answer.get("type") != "choice" or
                answer.get("choice") not in question["criteria"]):
            raise ValueError(f"Author runtime refused or omitted question {key}")


def handler(evaluate, identity):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body):
            data = json.dumps(body, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.reply(200 if self.path in ("/health", "/v1/info") else 404, identity)

        def do_POST(self):
            if self.path != "/v1/systemone":
                self.reply(404, {"error": "Unknown path"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= identity["max_body_mib"] * 1024 ** 2:
                    raise ValueError("Request body is empty or exceeds the model limit")
                body = json.loads(self.rfile.read(length))
                validate_request(body, identity["model"])
                response = evaluate(body)
                validate_response(response, body["questions"])
                response = {**response, "model": identity["model"], "model_revision": identity["revision"]}
                self.reply(200, response)
            except (ValueError, TypeError, KeyError) as error:
                self.reply(422, {"error": f"{type(error).__name__}: {error}"})
            except Exception as error:
                self.reply(500, {"error": f"{type(error).__name__}: {error}"})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=tuple(MODELS))
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    spec, path = MODELS[args.model], args.weights.resolve()
    identity = {"model": spec["model_id"], "revision": spec["revision"], "max_body_mib": spec["max_body_mib"]}
    info = json.loads((path / "jevlight-download.json").read_text(encoding="utf-8"))
    if info != {"model_id": spec["model_id"], "revision": spec["revision"]}:
        raise ValueError("Weights do not match the pinned download identity")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("An NVIDIA CUDA GPU is required")
    free, _ = torch.cuda.mem_get_info()
    if free / 1024 ** 3 < spec["min_free_gpu_gib"]:
        raise RuntimeError(f"Need at least {spec['min_free_gpu_gib']} GiB free GPU memory before model load")
    evaluate = load_runtime(args.model, path)
    # Serialize GPU work: author runtimes keep mutable caches and GPU state.
    class Server(HTTPServer):
        request_queue_size = 64

    server = Server(("127.0.0.1", args.port), handler(evaluate, identity))
    print(json.dumps({"ready": True, **identity}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
