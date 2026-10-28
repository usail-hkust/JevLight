"""Generic OpenAI-compatible LLM client for the LLMLight/CoLLMLight baselines.

Only the ``LLM`` surface the baselines' ``LanguageModelAdapter`` uses is
implemented (``inference`` and ``batch_inference``/``threading_inference``).
Behavioural notes:

- the counting tokenizer only loads from an explicit ``tokenizer.json`` via
  ``$BASELINE_LLM_TOKENIZER_PATH`` / ``$COLLMLIGHT_TOKENIZER_JSON``
  (``tokenizers`` package); no ``transformers`` dependency — without a file,
  counting falls back to a conservative character estimate;
- ``LLM`` accepts ``base_url``/``api_key`` overrides so any OpenAI-compatible
  endpoint works without provider-name conventions in the model path; an
  explicit ``base_url`` always routes to that endpoint;
- model paths that name no known provider and carry no ``base_url`` raise a
  ``RuntimeError`` telling the caller to serve the model behind an
  OpenAI-compatible endpoint (in-process vLLM loading is not supported).
"""

import threading
import time
from openai import OpenAI
import os
import warnings

# Total context budget constant for rollout-time accounting; the live
# deployment context below is configured separately.
MAX_CONTEXT_TOKENS = 32 * 1024
# The default live inference server context is 128000 tokens.
DEFAULT_LIVE_MAX_CONTEXT_TOKENS = 128_000
LIVE_MAX_CONTEXT_TOKENS = int(
    os.getenv(
        "BASELINE_LLM_MAX_CONTEXT_TOKENS",
        str(DEFAULT_LIVE_MAX_CONTEXT_TOKENS),
    )
)
MESSAGE_OVERHEAD_TOKENS = 6
# Remote API providers validate input + output <= model context; cap the
# per-turn output budget so a token-count miss cannot span the whole window.
API_MAX_GENERATION_TOKENS = 32_768
# Per-turn generation hard cap: one live turn must not consume the whole
# shared window. 0 disables (legacy full-window floor semantics).
LIVE_GEN_TOKEN_CAP = int(os.getenv("BASELINE_LLM_GEN_TOKEN_CAP", "8192"))
# Per-message token cap for the live path: without it truncate_messages'
# "give up" branches return the conversation UNTRUNCATED, so one runaway
# response can freeze the window. 0 disables.
LIVE_SINGLE_MESSAGE_TOKEN_CAP = int(
    os.getenv("BASELINE_LLM_SINGLE_MESSAGE_TOKEN_CAP", "8192")
)
_QWEN_TOKENIZER = None
_QWEN_TOKENIZER_LOAD_FAILED = False


def _load_local_tokenizer_file():
    """Load an exact tokenizer.json (e.g. the shared Qwen copy) if configured."""
    for env_name in ("BASELINE_LLM_TOKENIZER_PATH", "COLLMLIGHT_TOKENIZER_JSON"):
        path = os.getenv(env_name)
        if not path:
            continue
        try:
            from tokenizers import Tokenizer

            return Tokenizer.from_file(os.path.expanduser(path))
        except Exception as exc:
            warnings.warn(f"Failed to load tokenizer file {path}: {exc}")
    return None


def _get_qwen_tokenizer():
    """Lazy load the counting tokenizer from an explicit tokenizer.json."""
    global _QWEN_TOKENIZER, _QWEN_TOKENIZER_LOAD_FAILED
    if _QWEN_TOKENIZER is None and not _QWEN_TOKENIZER_LOAD_FAILED:
        _QWEN_TOKENIZER = _load_local_tokenizer_file()
        if _QWEN_TOKENIZER is None:
            _QWEN_TOKENIZER_LOAD_FAILED = True
            warnings.warn(
                "No counting tokenizer configured (set $BASELINE_LLM_TOKENIZER_PATH "
                "or $COLLMLIGHT_TOKENIZER_JSON to a tokenizer.json). Falling back "
                "to conservative character-based estimates."
            )
    return _QWEN_TOKENIZER


def _encoded_ids(tokenizer, text):
    """Tokenizer-agnostic encode: HF returns a list, tokenizers returns Encoding."""
    encoded = tokenizer.encode(text, add_special_tokens=False)
    return getattr(encoded, "ids", encoded)


def _count_tokens(messages):
    """Count message content tokens; conservative char estimate without a tokenizer."""
    tokenizer = _get_qwen_tokenizer()
    if tokenizer is not None:
        total = 0
        for message in messages:
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
            total += len(_encoded_ids(tokenizer, role))
            total += len(_encoded_ids(tokenizer, content))
            total += MESSAGE_OVERHEAD_TOKENS
        return total

    # No tokenizer available: estimate instead of returning 0.  A zero count
    # makes the generation budget span the whole context window, and remote
    # providers reject input+output > context with a 400.  ~2 chars per token
    # biases high for English/code and only mildly low for dense CJK text.
    return sum(
        (len(str(message.get("role", ""))) + len(str(message.get("content", "")))) // 2
        + MESSAGE_OVERHEAD_TOKENS
        + 8
        for message in messages
    )


def cap_message_content(message, max_tokens):
    """Cap ONE message's content at ``max_tokens`` tokens (frozen-role policy).

    Pure: returns ``(original_message, False)`` when the content already fits
    (or the tokenizer is unavailable / max_tokens <= 0), ``(new_dict, True)``
    otherwise. Oversized content is cut keep-head + keep-tail (3/4 head, 1/4
    tail around an explicit ``[...truncated...]`` marker).
    """
    tokenizer = _get_qwen_tokenizer()
    if tokenizer is None or max_tokens is None or max_tokens <= 0:
        return message, False
    content = message.get("content")
    if not isinstance(content, str) or not content:
        return message, False
    try:
        ids = tokenizer.encode(content, add_special_tokens=False)
        if len(ids) <= max_tokens:
            return message, False
        marker = (
            f"\n\n[...content truncated: dropped {len(ids) - max_tokens} of "
            f"{len(ids)} tokens; keep head+tail...]\n\n"
        )
        marker_ids = tokenizer.encode(marker, add_special_tokens=False)
        # 16-token slack for role/overhead so the WHOLE message (as
        # ``_count_tokens`` measures it) stays within max_tokens.
        room = max(2, max_tokens - len(marker_ids) - 16)
        head = max(1, room * 3 // 4)
        tail = max(1, room - head)
        new_content = (
            tokenizer.decode(ids[:head])
            + marker
            + tokenizer.decode(ids[-tail:])
        )
        capped = dict(message)
        capped["content"] = new_content
        return capped, True
    except Exception:  # noqa: BLE001 - capping must never kill the call
        return message, False


def truncate_messages(messages, max_input_tokens, single_message_cap=None):
    """Message-level left truncation under a token budget (shared policy).

    Pure: returns a NEW list when truncation fires, the original list otherwise;
    never mutates the caller's conversation.  Preserves the first 3 messages
    and the last user message; middle messages only as user/assistant pairs,
    newest first, while they fit the budget.
    """
    if len(messages) <= 4:
        if single_message_cap is None:
            return messages
        if _get_qwen_tokenizer() is None:
            return messages
        if _count_tokens(messages) <= max_input_tokens:
            return messages
        per_cap = min(single_message_cap, max(1, max_input_tokens // 4))
        return [cap_message_content(m, per_cap)[0] for m in messages]

    if _get_qwen_tokenizer() is None:
        return messages

    if _count_tokens(messages) <= max_input_tokens:
        return messages

    first_three = messages[:3]
    last_user = messages[-1]
    if last_user.get("role") != "user":
        return messages

    fixed_tokens = _count_tokens(first_three) + _count_tokens([last_user])
    if fixed_tokens > max_input_tokens:
        if single_message_cap is None:
            return messages
        per_cap = min(single_message_cap, max(1, max_input_tokens // 4))
        capped_three = [cap_message_content(m, per_cap)[0] for m in first_three]
        capped_last = cap_message_content(last_user, per_cap)[0]
        fixed_tokens = _count_tokens(capped_three) + _count_tokens([capped_last])
        if fixed_tokens > max_input_tokens:
            # Extreme fallback (only when overhead alone overflows): drop the
            # middle entirely, keep the capped head + tail.
            return capped_three + [capped_last]
        first_three = capped_three
        last_user = capped_last

    pairs = []
    middle = messages[3:-1]
    i = 0
    while i + 1 < len(middle):
        if middle[i].get("role") == "user" and middle[i + 1].get("role") == "assistant":
            pair = [middle[i], middle[i + 1]]
            pairs.append((pair, _count_tokens(pair)))
            i += 2
        else:
            i += 1

    kept_pairs_reversed = []
    total_tokens = fixed_tokens
    for pair, pair_tokens in reversed(pairs):
        if total_tokens + pair_tokens > max_input_tokens:
            break
        kept_pairs_reversed.append(pair)
        total_tokens += pair_tokens

    truncated = first_three
    for pair in reversed(kept_pairs_reversed):
        truncated.extend(pair)
    truncated.append(last_user)
    return truncated


def generation_budget(messages, max_context_tokens=MAX_CONTEXT_TOKENS):
    """Remaining generation room for ONE turn under the shared context cap.

    Floor of 1024 keeps a degenerate full-window prompt from requesting a
    zero-token generation.
    """
    return max(1024, max_context_tokens - _count_tokens(messages))


class LLM(object):
    def __init__(
        self,
        llm_path,
        batch_size=16,
        top_k=50,
        top_p=1.0,
        temperature=0.8,
        max_tokens=8192,
        fixed_max_tokens=False,
        retry_sleep_seconds=5.0,
        enable_thinking=None,
        max_retries=None,
        base_url=None,
        api_key=None,
    ):
        self.llm_path = str(llm_path).strip()
        self.fixed_max_tokens = fixed_max_tokens
        self.retry_sleep_seconds = float(retry_sleep_seconds)
        self.enable_thinking = enable_thinking
        self.max_retries = max_retries
        self.tokenizer, self.model, self.generation_kwargs, self.use_api = self.initialize_llm(
            llm_path, top_k, top_p, temperature, max_tokens, base_url=base_url, api_key=api_key
        )
        llm_parts = llm_path.split("/")
        llm_name = llm_parts[-1]
        self.institute_name = llm_parts[-2] if len(llm_parts) > 1 else ""
        self.provider_name = llm_parts[0]
        self.llm_name = llm_name
        self.batch_size = batch_size
        self.system_prompt = ("You are an expert in traffic management. Use your knowledge and reasoning skills to "
                              "solve the traffic signal timing problem. DO NOT write any code.")

        # data analysis type initialization
        self.data_analysis_types = None
        self.last_error = None
        # Set by _note_generation_truncated when a turn is cut at the live
        # per-turn gen cap; read by the agents' parse-fail branches.
        self.last_truncated = False

    def _api_extra_kwargs(self):
        """Non-standard OpenAI-compatible options requested by this instance.

        Also carries the instance sampling settings: without an explicit
        temperature the OpenAI-compatible server falls back to its own default,
        which sent deployed RL checkpoints into repetition loops. Sending
        explicit temperature/top_p pins decoding to the training-conditioned
        value. Sampling is omitted only when the client was constructed with
        top_p<=0 (legacy greedy marker).
        """
        kwargs = {}
        if self.enable_thinking is not None:
            kwargs["extra_body"] = {"enable_thinking": bool(self.enable_thinking)}
        gk = self.generation_kwargs
        temperature = gk.get("temperature") if isinstance(gk, dict) else getattr(gk, "temperature", None)
        top_p = gk.get("top_p") if isinstance(gk, dict) else getattr(gk, "top_p", None)
        if temperature is not None:
            kwargs["temperature"] = temperature
        if top_p:
            kwargs["top_p"] = top_p
        return kwargs

    def _stream_response_start(self):
        if self.enable_thinking is False:
            return "", True
        return "<think>\n", False

    def _sleep_for_retry(self, retry_count, max_retries):
        if retry_count < max_retries and self.retry_sleep_seconds > 0:
            time.sleep(self.retry_sleep_seconds)

    def _max_attempts(self, default_retries):
        retries = default_retries if self.max_retries is None else self.max_retries
        return 1 + max(0, int(retries))

    def _api_model_name(self):
        if self.provider_name == "deepseek":
            return self.llm_name
        if self.provider_name == "siliconflow":
            return f"{self.institute_name}/" + self.llm_name
        if self.provider_name == "llm_models":
            return self.llm_path
        if "deepseek" in self.llm_name.lower():
            return "deepseek-ai/" + self.llm_name
        return self.llm_name

    def _max_input_tokens(self):
        max_completion_tokens = (
            self.generation_kwargs["max_tokens"]
            if isinstance(self.generation_kwargs, dict)
            else getattr(self.generation_kwargs, "max_tokens", 8192)
        )
        return max(0, LIVE_MAX_CONTEXT_TOKENS - max_completion_tokens)

    def _generation_budget(self, messages):
        """Remaining generation room for one turn under the shared live context.

        The configured ``max_tokens`` is a FLOOR when ``fixed_max_tokens`` is
        unset: a turn generates everything the window has left after its
        (already message-level truncated) view, hard-capped at
        ``LIVE_GEN_TOKEN_CAP``. A fixed budget stays bounded by the same cap.
        """
        floor = (
            self.generation_kwargs["max_tokens"]
            if isinstance(self.generation_kwargs, dict)
            else getattr(self.generation_kwargs, "max_tokens", 8192)
        )
        if self.fixed_max_tokens:
            # Caller-mandated fixed budget: still bound by the live per-turn
            # cap (fixed_max_tokens is a cross-env API contract, not a license
            # to span the whole window).
            return int(min(floor, LIVE_GEN_TOKEN_CAP)) if LIVE_GEN_TOKEN_CAP > 0 else int(floor)
        try:
            # -600 chat-template margin: this class talks to engines/servers
            # directly, so the budget must leave room for the rendered
            # template tokens on top of the counted view.
            budget = max(
                int(floor),
                generation_budget(messages, LIVE_MAX_CONTEXT_TOKENS) - 600,
            )
            # Remote API providers validate input + output <= context
            # server-side: any counting miss would request an output budget
            # spanning the window and fail with a 400.  Local rollout servers
            # keep the full-window policy.
            if self.provider_name not in {"llm_models", "local_llm"}:
                budget = min(budget, API_MAX_GENERATION_TOKENS)
            # Live per-turn hard cap; 0 disables.
            if LIVE_GEN_TOKEN_CAP > 0:
                budget = min(budget, LIVE_GEN_TOKEN_CAP)
            return budget
        except Exception:
            return int(floor)

    def _note_generation_truncated(self, text, gen_budget):
        """Append the in-history truncation marker when the turn was cut at the
        per-turn generation cap and set ``self.last_truncated``. Servers report
        finish_reason="stop" for vLLM budget cuts, so infer locally: the decode
        stopping within 16 tokens of the requested cap means the turn was cut."""
        self.last_truncated = False
        if LIVE_GEN_TOKEN_CAP <= 0 or not text or gen_budget <= 0:
            return text
        try:
            if _count_tokens([{"role": "assistant", "content": text}]) >= gen_budget - 16:
                self.last_truncated = True
                return (
                    text
                    + f"\n\n[...generation truncated at {gen_budget} tokens: "
                    "response too long, the rest was discarded - retry concisely...]"
                )
        except Exception:  # noqa: BLE001 - detection must never kill the call
            pass
        return text

    def _sampling_params_for(self, messages):
        """generation_kwargs with the per-turn remaining-window budget swapped in."""
        params = dict(self.generation_kwargs) if isinstance(self.generation_kwargs, dict) else {}
        params["max_tokens"] = self._generation_budget(messages)
        return params

    def _truncate_messages(self, messages):
        """In-place message-level truncation (module-level shared policy)."""
        single_cap = LIVE_SINGLE_MESSAGE_TOKEN_CAP or None
        truncated = truncate_messages(messages, self._max_input_tokens(), single_message_cap=single_cap)
        if truncated is not messages:
            messages[:] = truncated
        return messages

    def initialize_llm(self, llm_path, top_k, top_p, temperature, max_tokens, base_url=None, api_key=None):
        # init LLM
        use_api = False
        generation_kwargs = {
            "top_k": top_k,
            "top_p": top_p,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        llm_path_lower = llm_path.lower()
        if base_url is not None:
            # Explicit endpoint override: any OpenAI-compatible server, no
            # provider-name convention required in the model path.
            llm_model = OpenAI(
                api_key=api_key or os.environ.get("LOCAL_LLM_API_KEY", "EMPTY"),
                base_url=base_url,
            )
            use_api = True
        elif (
            "local_llm" in llm_path_lower
            or llm_path_lower.startswith("llm_models/")
        ):
            llm_model = OpenAI(
                api_key=api_key or os.environ.get("LOCAL_LLM_API_KEY", "EMPTY"),
                base_url=os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:8000/v1"),
            )
            use_api = True
        elif "deepseek" in llm_path_lower and "siliconflow" not in llm_path_lower:
            api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "DEEPSEEK_API_KEY is required for DeepSeek API models. "
                    "Export it before running the baseline."
                )
            llm_model = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
            )
            use_api = True
        elif "openai" in llm_path_lower or "siliconflow" in llm_path_lower:
            if "openai" in llm_path_lower:
                api_key_name = "OPENAI_API_KEY"
                fallback_url = "https://api.openai.com/v1"
            else:
                api_key_name = "SILICONFLOW_API_KEY"
                fallback_url = "https://api.siliconflow.cn/v1"
            resolved_key = api_key or os.environ.get(api_key_name)
            if "siliconflow" in llm_path_lower and not resolved_key:
                # Backward compatibility with the mixed-case name used by
                # earlier launch scripts in the source repository.
                resolved_key = os.environ.get("SiliconFlow_API_KEY")
            if not resolved_key:
                legacy_hint = (
                    " (legacy SiliconFlow_API_KEY is also supported)"
                    if "siliconflow" in llm_path_lower
                    else ""
                )
                raise RuntimeError(
                    f"{api_key_name} is required for {llm_path}.{legacy_hint}"
                )
            llm_model = OpenAI(
                api_key=resolved_key,
                base_url=fallback_url,
            )
            use_api = True
        else:
            raise RuntimeError(
                f"No OpenAI-compatible backend for model path {llm_path!r}. "
                "In-process vLLM loading is not supported; serve the model "
                "behind an OpenAI-compatible endpoint and pass --llm_base_url "
                "(or use the served LLMLight/CoLLMLight paths)."
            )

        return None, llm_model, generation_kwargs, use_api

    def inference(self, query, system_prompt=None):
        message = [
            {
                "role": "system",
                "content": system_prompt if system_prompt is not None else self.system_prompt,
            },
            {
                "role": "user",
                "content": query
            }
        ]
        self._truncate_messages(message)

        if self.use_api:
            llm_name = self._api_model_name()

            retry_count = 0
            response = None
            self.last_error = None
            max_attempts = self._max_attempts(default_retries=2)
            gen_budget = self._generation_budget(message)
            while retry_count < max_attempts:
                try:
                    response = self.model.chat.completions.create(
                        model=llm_name,
                        messages=message,
                        max_tokens=gen_budget,
                        **self._api_extra_kwargs(),
                        # timeout=120
                    ).choices[0].message.content
                    break
                except Exception:
                    retry_count += 1
                    self._sleep_for_retry(retry_count, max_attempts)
            if response:
                response = self._note_generation_truncated(response, gen_budget)

        return response

    def batch_inference(self, queries, system_prompt=None):
        all_responses = []
        messages = list()

        for i, q in enumerate(queries):
            messages.append([
                {
                    "role": "system",
                    "content": system_prompt if system_prompt is not None else self.system_prompt,
                },
                {
                    "role": "user",
                    "content": q
                }
            ])
            self._truncate_messages(messages[-1])

            if len(messages) == self.batch_size or i == len(queries) - 1:
                if self.use_api:
                    llm_name = self._api_model_name()
                    threads = []
                    responses = [None for _ in range(len(messages))]

                    for j, message in enumerate(messages):
                        thread = threading.Thread(target=self.threading_inference,
                                                  args=(llm_name, message, responses, j,))
                        threads.append(thread)
                        thread.start()

                    for thread in threads:
                        thread.join()

                    all_responses.extend(responses)

                # Clear the batch. Without this, API-backed calls stop
                # dispatching once the first full batch is reached.
                messages = list()

        return all_responses

    def threading_inference(self, llm_name, message, response_list, m_id):
        retry_count = 0
        response_list[m_id] = ""
        max_attempts = self._max_attempts(default_retries=1)
        while retry_count < max_attempts:
            try:
                gen_budget = self._generation_budget(message)
                stream = self.model.chat.completions.create(
                    model=llm_name,
                    messages=message,
                    max_tokens=gen_budget,
                    stream=True,
                    **self._api_extra_kwargs(),
                )

                collected_response, reasoning_finish_flag = self._stream_response_start()
                for chunk in stream:
                    if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                        if not reasoning_finish_flag:
                            collected_response += "</think>\n"
                            reasoning_finish_flag = True
                        token = chunk.choices[0].delta.content
                        collected_response += token
                    elif self.enable_thinking is not False and hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[
                        0].delta.reasoning_content:
                        token = chunk.choices[0].delta.reasoning_content
                        collected_response += token
                response_list[m_id] = self._note_generation_truncated(collected_response, gen_budget)
                print(f"\nSuccess [{m_id}].")
                break

            except Exception as e:
                retry_count += 1
                print(e)
                self._sleep_for_retry(retry_count, max_attempts)
