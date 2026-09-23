"""Canonical hourly/final reporting for continuous rolling experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jevlight.evaluation_metrics import calculate_canonical_metrics_from_env
from jevlight.wandb_utils import safe_wandb_log


METRIC_NAMES = (
    "reward",
    "avg_travel_time",
    "avg_waiting_time",
    "avg_queue_len",
    "queuing_vehicle_num",
    "vehicle_count",
    "arrived_vehicle_count",
    "observed_vehicle_count",
    "intersection_observation_count",
    "queue_observation_step_count",
    "pending_vehicle_count",
    "running_vehicle_count",
    "tracked_arrived_count",
)


def define_rolling_wandb_metrics(logger: Any | None) -> None:
    """Define the shared W&B schema used by all three MZW scripts."""
    if logger is None:
        return
    logger.define_metric("hourly_results/checkpoint")
    for metric_name in METRIC_NAMES:
        logger.define_metric(
            f"hourly_results/{metric_name}",
            step_metric="hourly_results/checkpoint",
        )
    logger.define_metric("window_results/window_idx")
    for scope in ("window_results", "cumulative_results"):
        for metric_name in METRIC_NAMES:
            logger.define_metric(
                f"{scope}/{metric_name}",
                step_metric="window_results/window_idx",
            )


class RollingMetricRecorder:
    """Record cumulative canonical metrics every hour and once at completion.

    The recorder is attached to one persistent ``SUMOEnv``.  SUMOEnv notifies it
    after every simulated second, so checkpoints are exact even when a fixed
    timing plan has irregular phase durations.
    """

    def __init__(
        self,
        output_dir: str | Path,
        total_duration: int,
        hourly_interval: int = 3600,
        logger: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if total_duration <= 0:
            raise ValueError("total_duration must be positive")
        if hourly_interval <= 0:
            raise ValueError("hourly_interval must be positive")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.total_duration = int(total_duration)
        self.hourly_interval = int(hourly_interval)
        self.logger = None
        self.metadata = dict(metadata or {})
        self.start_time: int | None = None
        self.next_checkpoint_time: int | None = None
        self.hourly_records: list[dict[str, Any]] = []
        # ``window_records`` and window_results.jsonl are deliberately
        # single-window only. Lifetime/cumulative values are retained only in
        # the W&B payloads below and are never exposed to the LLM workflow.
        self.window_records: list[dict[str, Any]] = []
        self._wandb_window_records: list[dict[str, Any]] = []
        self._logged_hour_count = 0
        self._logged_window_count = 0
        self._final_record: dict[str, Any] | None = None
        self._final_logged = False
        self.set_logger(logger)

    def attach(
        self,
        env: Any,
        evaluation_start_time: int | None = None,
    ) -> "RollingMetricRecorder":
        """Attach to a SUMO environment without resetting its traffic state."""
        self.start_time = (
            int(round(float(env.get_current_time())))
            if evaluation_start_time is None
            else int(evaluation_start_time)
        )
        self.next_checkpoint_time = self.start_time + self.hourly_interval
        if not hasattr(env, "add_step_listener"):
            raise TypeError("SUMO environment does not support step listeners")
        env.add_step_listener(self)
        return self

    def set_logger(self, logger: Any | None) -> None:
        """Set W&B logger and backfill checkpoints produced before its init."""
        self.logger = logger
        define_rolling_wandb_metrics(logger)
        if logger is None:
            return
        self._flush_pending_wandb_records()

    def _flush_pending_wandb_records(self) -> None:
        """Retry buffered cumulative records without marking failed sends done."""
        if self.logger is None:
            return
        while self._logged_hour_count < len(self.hourly_records):
            if not safe_wandb_log(
                self.logger,
                self.hourly_records[self._logged_hour_count],
            ):
                return
            self._logged_hour_count += 1
        while self._logged_window_count < len(self._wandb_window_records):
            if not safe_wandb_log(
                self.logger,
                self._wandb_window_records[self._logged_window_count],
            ):
                return
            self._logged_window_count += 1
        if self._final_record is not None and not self._final_logged:
            self._final_logged = safe_wandb_log(
                self.logger,
                self._final_record,
            )

    def record_window(
        self,
        *,
        window_idx: int,
        start_time: float | None,
        end_time: float | None,
        window_metrics: dict[str, Any],
        cumulative_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a window locally and send window+cumulative scopes to W&B."""
        record: dict[str, Any] = {
            "window_results/window_idx": int(window_idx),
            "window_results/start_time": start_time,
            "window_results/end_time": end_time,
            "window_results/duration": (
                float(end_time) - float(start_time)
                if start_time is not None and end_time is not None
                else None
            ),
        }
        for metric_name in METRIC_NAMES:
            record[f"window_results/{metric_name}"] = window_metrics.get(
                metric_name,
                0,
            )
        wandb_record = dict(record)
        for metric_name in METRIC_NAMES:
            wandb_record[f"cumulative_results/{metric_name}"] = cumulative_metrics.get(
                metric_name,
                0,
            )
        self.window_records.append(record)
        self._wandb_window_records.append(wandb_record)
        with (self.output_dir / "window_results.jsonl").open(
            "a", encoding="utf-8"
        ) as output_file:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        if self.logger is not None:
            self._flush_pending_wandb_records()
        return record

    def on_simulation_second(self, env: Any) -> None:
        """SUMOEnv listener callback; emit any checkpoint reached this second."""
        if self.next_checkpoint_time is None or self.start_time is None:
            return
        current_time = int(round(float(env.get_current_time())))
        evaluation_end = self.start_time + self.total_duration
        while (
            self.next_checkpoint_time <= evaluation_end
            and current_time >= self.next_checkpoint_time
        ):
            self._record_hour(env, self.next_checkpoint_time)
            self.next_checkpoint_time += self.hourly_interval

    def _record_hour(self, env: Any, checkpoint_time: int) -> None:
        checkpoint = len(self.hourly_records) + 1
        record = calculate_canonical_metrics_from_env(env, "hourly_results")
        record.update({
            "hourly_results/checkpoint": checkpoint,
            "hourly_results/start_time": self.start_time,
            "hourly_results/end_time": checkpoint_time,
            "hourly_results/duration": checkpoint_time - int(self.start_time),
            "hourly_results/scope": "cumulative_from_simulation_start",
        })
        self.hourly_records.append(record)
        if self.logger is not None:
            self._flush_pending_wandb_records()

    def finalize(self, env: Any) -> dict[str, Any]:
        """Log and return the one full-runtime ``final/*`` result."""
        if self.start_time is None:
            raise RuntimeError("recorder must be attached before finalize")
        current_time = int(round(float(env.get_current_time())))
        record = calculate_canonical_metrics_from_env(env, "final")
        record.update({
            "final/checkpoint": 0,
            "final/start_time": self.start_time,
            "final/end_time": current_time,
            "final/duration": current_time - self.start_time,
            "final/scope": "complete_continuous_simulation",
        })
        self._final_record = record
        self._flush_pending_wandb_records()
        return record
