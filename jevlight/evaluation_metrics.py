"""Shared final/test evaluation metrics for all SUMO controller runners."""

from __future__ import annotations

from typing import Any

import numpy as np


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if np.isfinite(value) else default


def _pending_vehicle_count(env: Any | None) -> float:
    """Return SUMO's end-of-scope min-expected vehicle count when available."""
    try:
        simulation = getattr(getattr(env, "traci_conn", None), "simulation", None)
        return _safe_float(simulation.getMinExpectedNumber()) if simulation else 0.0
    except Exception:
        return 0.0


def capture_canonical_metric_snapshot(env: Any | None) -> dict[str, Any]:
    """Capture cumulative counters at a rolling-window boundary.

    SUMOEnv intentionally keeps its canonical counters across live rolling
    windows.  Keeping this lightweight snapshot lets callers derive an exact
    per-window queue/reward result while preserving the cumulative result.
    Vehicle dictionaries are also captured so waiting/travel contributions can
    be restricted to vehicles observed during the window.
    """
    if env is None:
        return {
            "time": 0.0,
            "queue": {"sum": 0.0, "count": 0, "step_count": 0},
            "reward": 0.0,
            "waiting": {},
            "seen_vehicle_ids": set(),
            "active_departures": {},
            "active_vehicle_ids": set(),
            "arrived_travel_times": {},
            "pending_vehicle_count": 0.0,
        }

    queue = (
        env.get_intersection_queue_totals()
        if hasattr(env, "get_intersection_queue_totals")
        else {"sum": 0.0, "count": 0, "step_count": 0}
    )
    waiting = (
        env.get_all_vehicle_waiting_times()
        if hasattr(env, "get_all_vehicle_waiting_times")
        else {}
    )
    arrived = (
        env.get_arrived_vehicle_travel_times()
        if hasattr(env, "get_arrived_vehicle_travel_times")
        else {}
    )
    active_departures = dict(getattr(env, "_depart_time_by_vehicle", {}) or {})
    system_states = getattr(env, "system_states", {}) or {}
    active_vehicle_ids = set(
        (system_states.get("get_vehicle_speed", {}) or {}).keys()
    )
    return {
        "time": _safe_float(
            env.get_current_time() if hasattr(env, "get_current_time") else 0.0
        ),
        "queue": {
            "sum": _safe_float(queue.get("sum", 0.0)),
            "count": int(queue.get("count", 0) or 0),
            "step_count": int(queue.get("step_count", 0) or 0),
        },
        "reward": _safe_float(getattr(env, "_canonical_reward_sum", 0.0)),
        "waiting": {str(key): _safe_float(value) for key, value in waiting.items()},
        "seen_vehicle_ids": set(getattr(env, "_seen_vehicle_ids", set()) or set()),
        "active_departures": {
            str(key): _safe_float(value) for key, value in active_departures.items()
        },
        "active_vehicle_ids": {str(value) for value in active_vehicle_ids},
        "arrived_travel_times": {
            str(key): _safe_float(value) for key, value in arrived.items()
        },
        "pending_vehicle_count": _pending_vehicle_count(env),
    }


def calculate_canonical_window_metrics_from_env(
    env: Any | None,
    snapshot: dict[str, Any],
    namespace: str,
) -> dict[str, float | int]:
    """Calculate metrics accrued since ``snapshot`` on a persistent SUMOEnv.

    Queue and reward are exact counter deltas. Waiting time is the average
    stopped time accrued in this window by vehicles observed in the window.
    Travel time is the average amount of vehicle travel elapsed inside the
    window, including vehicles already active at its boundary. These definitions
    are used for both live windows and TRAIN_AND_SIMULATION validation, making
    their comparison like-for-like.
    """
    if env is None:
        return {
            f"{namespace}/avg_travel_time": 0.0,
            f"{namespace}/avg_waiting_time": 0.0,
            f"{namespace}/avg_queue_len": 0.0,
            f"{namespace}/reward": 0.0,
            f"{namespace}/queuing_vehicle_num": 0.0,
            f"{namespace}/vehicle_count": 0,
            f"{namespace}/arrived_vehicle_count": 0,
            f"{namespace}/observed_vehicle_count": 0,
            f"{namespace}/intersection_observation_count": 0,
            f"{namespace}/queue_observation_step_count": 0,
            f"{namespace}/pending_vehicle_count": 0.0,
            f"{namespace}/running_vehicle_count": 0,
            f"{namespace}/tracked_arrived_count": 0,
        }

    start = snapshot or capture_canonical_metric_snapshot(None)
    end = capture_canonical_metric_snapshot(env)
    start_queue = start.get("queue", {}) or {}
    end_queue = end.get("queue", {}) or {}
    queue_sum = max(
        0.0,
        _safe_float(end_queue.get("sum")) - _safe_float(start_queue.get("sum")),
    )
    queue_count = max(
        0,
        int(end_queue.get("count", 0) or 0) - int(start_queue.get("count", 0) or 0),
    )
    queue_steps = max(
        0,
        int(end_queue.get("step_count", 0) or 0)
        - int(start_queue.get("step_count", 0) or 0),
    )

    start_waiting = start.get("waiting", {}) or {}
    end_waiting = end.get("waiting", {}) or {}
    start_seen = {str(value) for value in start.get("seen_vehicle_ids", set())}
    end_seen = {str(value) for value in end.get("seen_vehicle_ids", set())}
    active_at_start = {
        str(value) for value in start.get("active_vehicle_ids", set())
    }
    observed_ids = active_at_start | (end_seen - start_seen)
    waiting_deltas = [
        max(
            0.0,
            _safe_float(end_waiting.get(vehicle_id, 0.0))
            - _safe_float(start_waiting.get(vehicle_id, 0.0)),
        )
        for vehicle_id in observed_ids
    ]

    start_time = _safe_float(start.get("time", 0.0))
    end_time = _safe_float(end.get("time", start_time))
    start_departures = start.get("active_departures", {}) or {}
    end_departures = end.get("active_departures", {}) or {}
    start_arrived = start.get("arrived_travel_times", {}) or {}
    end_arrived = end.get("arrived_travel_times", {}) or {}
    newly_arrived = set(end_arrived) - set(start_arrived)
    travel_durations = []
    for vehicle_id in observed_ids:
        if vehicle_id in newly_arrived:
            total_travel = _safe_float(end_arrived.get(vehicle_id, 0.0))
            if vehicle_id in start_departures:
                elapsed_before_window = max(
                    0.0,
                    start_time - _safe_float(start_departures[vehicle_id]),
                )
                travel_durations.append(max(0.0, total_travel - elapsed_before_window))
            else:
                travel_durations.append(max(0.0, total_travel))
        elif vehicle_id in end_departures:
            travel_durations.append(
                max(
                    0.0,
                    end_time
                    - max(start_time, _safe_float(end_departures[vehicle_id])),
                )
            )

    return {
        f"{namespace}/avg_travel_time": (
            float(np.mean(travel_durations)) if travel_durations else 0.0
        ),
        f"{namespace}/avg_waiting_time": (
            float(np.mean(waiting_deltas)) if waiting_deltas else 0.0
        ),
        f"{namespace}/avg_queue_len": (
            queue_sum / queue_steps if queue_steps else 0.0
        ),
        f"{namespace}/reward": (
            _safe_float(end.get("reward")) - _safe_float(start.get("reward"))
        ),
        f"{namespace}/queuing_vehicle_num": queue_sum,
        f"{namespace}/vehicle_count": len(travel_durations),
        f"{namespace}/arrived_vehicle_count": len(newly_arrived),
        f"{namespace}/observed_vehicle_count": len(observed_ids),
        f"{namespace}/intersection_observation_count": queue_count,
        f"{namespace}/queue_observation_step_count": queue_steps,
        # Pending/running are end-of-window state rather than additive
        # counters. Tracked arrivals are restricted to this window.
        f"{namespace}/pending_vehicle_count": _safe_float(
            end.get("pending_vehicle_count", 0.0)
        ),
        f"{namespace}/running_vehicle_count": len(
            end.get("active_vehicle_ids", set())
        ),
        f"{namespace}/tracked_arrived_count": len(newly_arrived),
    }


def calculate_evaluation_metrics_from_env(
    env: Any | None,
    namespace: str,
) -> dict[str, float | int]:
    """Calculate the canonical RLLight metrics from raw SUMO aggregates."""
    vehicle_travel_times = (
        env.get_all_vehicle_travel_times()
        if env is not None and hasattr(env, "get_all_vehicle_travel_times")
        else {}
    )
    arrived_travel_times = (
        env.get_arrived_vehicle_travel_times()
        if env is not None and hasattr(env, "get_arrived_vehicle_travel_times")
        else {}
    )
    waiting_times = (
        env.get_all_vehicle_waiting_times()
        if env is not None and hasattr(env, "get_all_vehicle_waiting_times")
        else {}
    )
    queue_totals = (
        env.get_intersection_queue_totals()
        if env is not None and hasattr(env, "get_intersection_queue_totals")
        else {"sum": 0.0, "count": 0, "step_count": 0}
    )
    queue_step_count = queue_totals.get("step_count", 0)
    avg_travel_time = (
        float(np.mean(list(vehicle_travel_times.values())))
        if vehicle_travel_times
        else 0.0
    )

    return {
        f"{namespace}/avg_travel_time": avg_travel_time,
        f"{namespace}/avg_waiting_time": (
            float(np.mean(list(waiting_times.values())))
            if waiting_times
            else 0.0
        ),
        f"{namespace}/avg_queue_len": (
            queue_totals["sum"] / queue_step_count
            if queue_step_count
            else 0.0
        ),
        f"{namespace}/queuing_vehicle_num": queue_totals.get("sum", 0.0),
        f"{namespace}/vehicle_count": len(vehicle_travel_times),
        f"{namespace}/arrived_vehicle_count": len(arrived_travel_times),
        f"{namespace}/observed_vehicle_count": len(waiting_times),
        f"{namespace}/intersection_observation_count": int(
            queue_totals.get("count", 0)
        ),
        f"{namespace}/queue_observation_step_count": int(queue_step_count),
    }


def calculate_canonical_metrics_from_env(
    env: Any | None,
    namespace: str,
) -> dict[str, float | int]:
    """Return the complete canonical metric set used by rolling MZW tests.

    Reward is deliberately independent of a controller's training reward: it is
    the negative, per-second integral of the network queue.  This makes reward
    comparable even when an RL implementation was trained with a different
    reward configuration.
    """
    metrics = calculate_evaluation_metrics_from_env(env, namespace)
    metrics[f"{namespace}/reward"] = float(
        getattr(env, "_canonical_reward_sum", 0.0) if env is not None else 0.0
    )
    active_vehicle_ids = set()
    if env is not None:
        system_states = getattr(env, "system_states", {}) or {}
        active_vehicle_ids = set(
            (system_states.get("get_vehicle_speed", {}) or {}).keys()
        )
    metrics.update({
        f"{namespace}/pending_vehicle_count": _pending_vehicle_count(env),
        f"{namespace}/running_vehicle_count": len(active_vehicle_ids),
        f"{namespace}/tracked_arrived_count": metrics.get(
            f"{namespace}/arrived_vehicle_count", 0
        ),
    })
    return metrics
