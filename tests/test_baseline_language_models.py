"""Trimmed generic LLM client unit tests (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

openai = pytest.importorskip("openai")

from baselines.llmlight.language_models import (  # noqa: E402
    LLM,
    cap_message_content,
    truncate_messages,
)


class TestProviderRouting:
    def test_siliconflow_name_includes_institute(self):
        llm = LLM("siliconflow/deepseek-ai/DeepSeek-V4-Flash", base_url="http://localhost:9/v1")
        assert llm._api_model_name() == "deepseek-ai/DeepSeek-V4-Flash"

    def test_deepseek_provider_uses_bare_name(self):
        llm = LLM("deepseek/chat-model", base_url="http://localhost:9/v1")
        assert llm._api_model_name() == "chat-model"

    def test_local_model_prefixes_pass_full_path(self):
        llm = LLM("llm_models/qwen/some-model", base_url="http://localhost:9/v1")
        assert llm._api_model_name() == "llm_models/qwen/some-model"

    def test_deepseek_named_model_gets_institute_prefix(self):
        llm = LLM("SomeOrg/DeepSeek-R1", base_url="http://localhost:9/v1")
        assert llm._api_model_name() == "deepseek-ai/DeepSeek-R1"

    def test_plain_name_passthrough(self):
        llm = LLM("tev/tev1", base_url="http://localhost:9/v1")
        assert llm._api_model_name() == "tev1"


class TestBackendSelection:
    def test_base_url_override_wins(self):
        llm = LLM("anything/at/all", base_url="http://x:9/v1", api_key="K")
        assert llm.use_api is True
        assert str(llm.model.base_url).startswith("http://x:9/v1")
        assert llm.model.api_key == "K"

    def test_local_llm_env_default(self, monkeypatch):
        monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://env:9/v1")
        monkeypatch.delenv("LOCAL_LLM_API_KEY", raising=False)
        llm = LLM("local_llm/model")
        assert str(llm.model.base_url).startswith("http://env:9/v1")
        assert llm.model.api_key == "EMPTY"

    def test_llm_models_prefix_uses_local_env(self, monkeypatch):
        monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://env2:9/v1")
        llm = LLM("llm_models/qwen/m")
        assert str(llm.model.base_url).startswith("http://env2:9/v1")

    def test_unknown_provider_without_base_url_raises(self):
        with pytest.raises(RuntimeError, match="OpenAI-compatible"):
            LLM("plain-model-name")


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def stream_reply(text):
    delta = SimpleNamespace(content=text, reasoning_content=None)
    chunk = SimpleNamespace(choices=[SimpleNamespace(delta=delta)])
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))]), [chunk]


def chat_reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def make_llm(fake_completions, **kwargs):
    llm = LLM(
        "llm_models/test/model",
        base_url="http://localhost:9/v1",
        retry_sleep_seconds=0.0,
        enable_thinking=False,
        max_tokens=64,
        fixed_max_tokens=True,
        **kwargs,
    )
    llm.model = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))
    return llm


class TestInferenceRetry:
    def test_inference_retries_then_succeeds(self):
        reply, _ = stream_reply("hello")
        fake = FakeCompletions([RuntimeError("boom"), reply])
        llm = make_llm(fake, max_retries=1)
        assert llm.inference("query", system_prompt="sys") == "hello"
        assert len(fake.calls) == 2
        # The fixed budget and disabled thinking are forwarded.
        assert fake.calls[0]["max_tokens"] == 64
        assert fake.calls[0]["extra_body"] == {"enable_thinking": False}

    def test_inference_returns_none_after_exhausted_retries(self):
        fake = FakeCompletions([RuntimeError("boom"), RuntimeError("boom")])
        llm = make_llm(fake, max_retries=1)
        assert llm.inference("query", system_prompt="sys") is None
        assert len(fake.calls) == 2

    def test_batch_inference_threads_streaming_calls(self):
        _, chunks = stream_reply("hi")
        fake = FakeCompletions([chunks, chunks, chunks])
        llm = make_llm(fake, max_retries=0)
        llm.batch_size = 2
        responses = llm.batch_inference(["a", "b", "c"], system_prompt="sys")
        assert responses == ["hi", "hi", "hi"]


class TestTruncation:
    def test_short_conversations_pass_through(self):
        messages = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
        ]
        assert truncate_messages(messages, 4096) is messages

    def test_cap_message_content_without_tokenizer_is_noop(self):
        message = {"role": "user", "content": "x" * 100}
        assert cap_message_content(message, 4) == (message, False)
