"""Optional W&B logging helpers.

wandb is an optional dependency: when it is not installed every helper is a
safe no-op and ``wandb_init_if_enabled`` returns ``None``.
"""

from __future__ import annotations

try:
    import wandb
except ImportError:  # pragma: no cover - depends on the environment
    wandb = None


def is_wandb_enabled(env_config):
    return bool(env_config.get("USE_WANDB", True)) and wandb is not None


def wandb_init_if_enabled(env_config, **kwargs):
    if not is_wandb_enabled(env_config):
        return None
    return wandb.init(**kwargs)


def safe_wandb_log(logger, data):
    if logger is None:
        return False
    try:
        logger.log(data)
        return True
    except (BrokenPipeError, ConnectionError, OSError) as exc:
        print(f"Warning: wandb log failed and was skipped: {exc}")
        return False


def safe_wandb_finish(logger=None):
    if wandb is None:
        return
    try:
        if logger is not None:
            logger.finish()
        elif wandb.run is not None:
            wandb.finish()
    except (BrokenPipeError, ConnectionError, OSError) as exc:
        print(f"Warning: wandb finish failed and was skipped: {exc}")
