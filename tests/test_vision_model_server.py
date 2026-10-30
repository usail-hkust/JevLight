import json
from threading import Thread
from http.server import HTTPServer

import pytest
import requests

from scripts.serve_vision_model import MODELS, handler, validate_request, validate_response


def request(model):
    return {"model": model, "state": {"current_views": [{"image": "Image 1"}]},
            "images": ["data:image/jpeg;base64,YQ=="] * 8,
            "questions": {f"q{i}": {"type": "choice", "criteria": {"none": "No cars", "many": "Many cars"}}
                          for i in range(24)}}


@pytest.mark.parametrize("key", MODELS)
def test_all_models_share_eight_image_twenty_four_question_contract(key):
    identity = {"model": MODELS[key]["model_id"], "revision": MODELS[key]["revision"], "max_body_mib": 4}
    body = request(identity["model"])
    validate_request(body, identity["model"])
    calls = []

    def evaluate(req):
        calls.append(req)
        return {"answers": {key: {"type": "choice", "choice": "none"} for key in req["questions"]}}

    server = HTTPServer(("127.0.0.1", 0), handler(evaluate, identity))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        assert requests.get(url + "/health", timeout=5).json() == identity
        result = requests.post(url + "/v1/systemone", json=body, timeout=5)
        assert result.status_code == 200
        assert result.json()["model_revision"] == identity["revision"]
        assert len(result.json()["answers"]) == 24
        assert calls == [body]
        bad = {**body, "model": "wrong"}
        assert requests.post(url + "/v1/systemone", json=bad, timeout=5).status_code == 422
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_model_errors_and_remote_image_urls_are_rejected():
    body = request("test")
    with pytest.raises(ValueError, match="inline"):
        validate_request({**body, "images": ["https://example.com/private.png"]}, "test")
    with pytest.raises(ValueError, match="refused"):
        validate_response({"answers": {"q0": {"type": "choice", "error": "too_long"}}}, body["questions"])
