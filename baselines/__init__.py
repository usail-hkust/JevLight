"""Baseline controllers on the JevLight evaluation stack.

The controllers implement the standard traffic-signal baselines (LLMLight,
CoLLMLight, CoLight, PressLight, MPLight, AttendLight, AdvancedDQN, CityLight,
MaxPressure, Webster, FixedTime).  Each one implements the JevLight runner
contract — ``decide(observations, step) -> (actions, traces)`` plus
``usage_summary()`` — so every baseline runs through the identical simulation
loop and metric computation in :mod:`baselines.run_baseline`.

This package must stay import-light: TensorFlow and PyTorch are imported only
inside the RL branches of :func:`build_controller` and inside the guarded
import block of :mod:`baselines.rl.rl_config`, never at ``import baselines``.
"""

from __future__ import annotations

from typing import Any

BASELINES = (
    "llmlight",
    "collmlight",
    "maxpressure",
    "webster",
    "fixedtime",
    "colight",
    "presslight",
    "mplight",
    "attendlight",
    "advanceddqn",
    "citylight",
)

RL_BASELINES = (
    "colight",
    "presslight",
    "mplight",
    "attendlight",
    "advanceddqn",
    "citylight",
)

# Registry CLI name -> training model name in baselines.rl.
RL_MODEL_NAMES = {
    "colight": "Colight",
    "presslight": "PressLight",
    "mplight": "MPLight",
    "attendlight": "Attend",
    "advanceddqn": "AdvancedDQN",
    "citylight": "CityLight",
}

LLM_BASELINES = ("llmlight", "collmlight")


def build_controller(name: str, args: Any, env_config: dict) -> Any:
    """Construct the baseline controller selected by ``--baseline``.

    ``env_config`` is the evaluation env configuration built by the runner; RL
    controllers keep it as the metadata view for their agents (model-specific
    ``LIST_STATE_FEATURE`` and ``TOP_K_ADJACENCY`` are merged in by the
    controller itself).  Heavy imports happen inside each branch.
    """
    if name not in BASELINES:
        raise ValueError(
            f"Unknown baseline {name!r}; registered: {', '.join(BASELINES)}"
        )

    if name in RL_BASELINES:
        if not args.rl_checkpoint:
            raise ValueError(
                f"--rl_checkpoint is required for the {name} baseline "
                "(train one with: python -m baselines.rl.train --model "
                f"{RL_MODEL_NAMES[name]})"
            )
        from baselines.rl.eval_controller import RLBaselineController

        return RLBaselineController(
            model_name=RL_MODEL_NAMES[name],
            checkpoint_dir=args.rl_checkpoint,
            round_index=args.rl_round,
            agent_conf_path=args.rl_agent_conf,
            env_config=env_config,
            device=args.rl_device,
        )

    if name == "maxpressure":
        from baselines.maxpressure import StrictLaneMaxPressureController

        return StrictLaneMaxPressureController(args.duration)

    if name == "fixedtime":
        from baselines.fixedtime import FixedTimeController

        return FixedTimeController(args.duration, splits=args.fixed_time_splits)

    if name == "webster":
        from baselines.webster import WebsterController

        return WebsterController(
            args.duration,
            update_frequency=args.webster_update_frequency,
            min_green_time=args.webster_min_green,
            min_cycle_time=args.webster_min_cycle,
            max_cycle_time=args.webster_max_cycle,
            saturation_flow=args.webster_saturation_flow,
            vehicle_length=args.webster_vehicle_length,
        )

    # LLMLight / CoLLMLight: mirror run_LLMLight.py's adapter construction.
    import os

    from baselines.llmlight.controller import (
        DEFAULT_BACKBONE,
        DEFAULT_LLMLIGHT_BASE_URL,
        DEFAULT_LLMLIGHT_MODEL,
        CoLLMLightController,
        LanguageModelAdapter,
        LLMLightController,
        resolve_llmlight_model,
    )

    max_tokens = args.max_tokens
    if max_tokens is None:
        max_tokens = 1024 if name == "llmlight" else 8192
    top_p = args.top_p
    if top_p is None:
        top_p = 1.0 if name == "llmlight" else 0.95
    llmlight_provider = args.llmlight_provider
    llm_model = (
        resolve_llmlight_model(llmlight_provider, args.llmlight_model or DEFAULT_LLMLIGHT_MODEL)
        if name == "llmlight"
        else (args.backbone or DEFAULT_BACKBONE)
    )
    llm = LanguageModelAdapter(
        model=llm_model,
        max_tokens=max_tokens,
        temperature=args.temperature,
        top_p=top_p,
        batch_size=args.max_workers,
        mock=args.mock_llm,
        llmlight_base_url=(
            (args.llmlight_base_url or DEFAULT_LLMLIGHT_BASE_URL)
            if name == "llmlight" and llmlight_provider == "local"
            else None
        ),
        llmlight_api_key=(
            os.environ.get("LLMLIGHT_LLM_API_KEY")
            or os.environ.get("LOCAL_LLM_API_KEY")
            or "EMPTY"
        ),
        llmlight_tokenizer_path=(
            args.llmlight_tokenizer_path
            if name == "llmlight" and llmlight_provider == "local"
            else None
        ),
        llmlight_max_context_tokens=args.llmlight_max_context_tokens,
        llm_base_url=args.llm_base_url,
        llm_api_key=args.llm_api_key,
    )
    if name == "llmlight":
        return LLMLightController(llm, args.duration)
    return CoLLMLightController(
        llm,
        args.duration,
        history_window=args.history_window,
        communication_threshold=args.communication_threshold,
        disable_psr=args.disable_psr,
    )
