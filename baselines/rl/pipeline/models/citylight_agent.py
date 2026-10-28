"""CityLight's parameter-sharing MAPPO policy on the repository SUMO runtime.

Signal execution intentionally remains owned by :mod:`utils.sumo_env`.  The
observation, heterogeneous action masks, relative-neighbour attention and PPO
update below follow the official CityLight implementation in
``githubs/CityLight/TSC-example``.
"""

from __future__ import annotations

import copy
import os
import pickle
import random
from typing import Any, Dict, Iterable, Sequence, Tuple

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .agent import Agent


def _init_linear(layer: nn.Linear, gain: float) -> nn.Linear:
    nn.init.orthogonal_(layer.weight, gain=gain)
    nn.init.constant_(layer.bias, 0)
    return layer


class _SelfAttention(nn.Module):
    """Official CityLight attention operator (attention across heads)."""

    def __init__(self, embedding_dim: int, heads: int = 4, dim_head: int = 32):
        super().__init__()
        self.heads = heads
        self.dim_head = dim_head
        self.query = nn.Linear(embedding_dim, heads * dim_head, bias=False)
        self.key = nn.Linear(embedding_dim, heads * dim_head, bias=False)
        self.value = nn.Linear(embedding_dim, heads * dim_head, bias=False)
        self.linear = nn.Linear(heads * dim_head, embedding_dim)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        batch = value.shape[0]
        query = self.query(value).view(batch, self.heads, self.dim_head)
        key = self.key(value).view(batch, self.heads, self.dim_head).transpose(1, 2)
        val = self.value(value).view(batch, self.heads, self.dim_head)
        scores = torch.matmul(query, key) / np.sqrt(self.dim_head)
        weights = F.softmax(scores, dim=-1)
        return self.linear(torch.matmul(weights, val).reshape(batch, -1))


class _CrossAttention(nn.Module):
    def __init__(
        self,
        key_dim: int,
        query_dim: int,
        heads: int = 4,
        dim_head: int = 32,
    ):
        super().__init__()
        self.heads = heads
        self.dim_head = dim_head
        self.query = nn.Linear(query_dim, heads * dim_head, bias=False)
        self.key = nn.Linear(key_dim, heads * dim_head, bias=False)
        self.value = nn.Linear(key_dim, heads * dim_head, bias=False)
        self.linear = nn.Linear(heads * dim_head, key_dim)

    def forward(self, key_value: torch.Tensor, query_value: torch.Tensor) -> torch.Tensor:
        batch = key_value.shape[0]
        query = self.query(query_value).view(batch, self.heads, self.dim_head)
        key = self.key(key_value).view(batch, self.heads, self.dim_head).transpose(1, 2)
        value = self.value(key_value).view(batch, self.heads, self.dim_head)
        scores = torch.matmul(query, key) / np.sqrt(self.dim_head)
        weights = F.softmax(scores, dim=-1)
        return self.linear(torch.matmul(weights, value).reshape(batch, -1))


class _FeedForward(nn.Module):
    def __init__(self, dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim, dim),
            nn.GELU(),
            nn.Linear(dim, dim),
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.net(value)


class _TypeAttentionInvariant(nn.Module):
    """The official ``Invariant(..., type_attn, distance=2)`` branch."""

    def __init__(self, input_dim: int, neighbour_dim: int = 8, hidden_dim: int = 64):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.encode_actor = nn.Linear(input_dim, hidden_dim)
        self.encode_other = nn.Linear(neighbour_dim, hidden_dim)
        self.type_map = nn.Linear(2, hidden_dim)
        self.self_x = _SelfAttention(hidden_dim)
        self.self_x_ff = _FeedForward(hidden_dim)
        self.self_y = _SelfAttention(hidden_dim)
        self.self_y_ff = _FeedForward(hidden_dim)
        self.type_attention = _CrossAttention(hidden_dim, hidden_dim)
        self.type_ff = _FeedForward(hidden_dim)
        self.distance_encoder = nn.Linear(2, hidden_dim // 4)
        self.distance_map = nn.Linear(hidden_dim + hidden_dim // 4, hidden_dim)
        self.cross_attention = _CrossAttention(hidden_dim, hidden_dim)
        self.cross_ff = _FeedForward(hidden_dim)
        self.score = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )
        self.fuse_types = nn.Linear(2 * hidden_dim, hidden_dim)

    def _self_encode(self, value: torch.Tensor, attention, feed_forward) -> torch.Tensor:
        return feed_forward(attention(value) + value)

    def forward(
        self,
        own_observation: torch.Tensor,
        neighbour_observations: torch.Tensor,
        neighbour_masks: torch.Tensor,
        neighbour_relations: torch.Tensor,
        neighbour_distances: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        if neighbour_observations.shape[1] != 4:
            raise ValueError("Official CityLight type_attn requires four neighbour slots")

        own = self._self_encode(
            self.encode_actor(own_observation), self.self_x, self.self_x_ff
        )
        grouped_outputs = []
        for slot_start in (0, 2):
            outputs = []
            scores = []
            for slot in range(slot_start, slot_start + 2):
                other = self.encode_other(neighbour_observations[:, slot])
                relation = self.type_map(neighbour_relations[:, slot])
                other = self.type_ff(self.type_attention(other, relation) + other)
                other = self._self_encode(other, self.self_y, self.self_y_ff)
                distance = self.distance_encoder(neighbour_distances[:, slot])
                query = self.distance_map(torch.cat((own, distance), dim=-1))
                output = self.cross_ff(
                    self.cross_attention(other, query) + other
                )
                score = self.score(output)
                score = score.masked_fill(
                    neighbour_masks[:, slot : slot + 1] == 0,
                    -torch.inf,
                )
                outputs.append(output)
                scores.append(score)

            stacked_outputs = torch.stack(outputs, dim=1)
            coefficients = torch.softmax(torch.stack(scores, dim=1), dim=1)
            coefficients = torch.nan_to_num(coefficients, nan=0.0)
            grouped_outputs.append((stacked_outputs * coefficients).sum(dim=1))

        neighbour = self.fuse_types(torch.cat(grouped_outputs, dim=-1))
        return own, neighbour


class _MLPBase(nn.Module):
    """Official LayerNorm + orthogonal ReLU MLP with ``layer_N=2``."""

    def __init__(self, input_dim: int, hidden_dim: int = 64, layer_count: int = 2):
        super().__init__()
        gain = nn.init.calculate_gain("relu")
        self.input_norm = nn.LayerNorm(input_dim)
        self.first = nn.Sequential(
            _init_linear(nn.Linear(input_dim, hidden_dim), gain),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        hidden = nn.Sequential(
            _init_linear(nn.Linear(hidden_dim, hidden_dim), gain),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.hidden = nn.ModuleList(copy.deepcopy(hidden) for _ in range(layer_count))

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        value = self.first(self.input_norm(value))
        for layer in self.hidden:
            value = layer(value)
        return value


class _CityLightBackbone(nn.Module):
    def __init__(self, observation_dim: int, hidden_dim: int = 64):
        super().__init__()
        self.neighbour_feature_indices = (
            0,
            1,
            2,
            3,
            observation_dim - 4,
            observation_dim - 3,
            observation_dim - 2,
            observation_dim - 1,
        )
        self.invariant = _TypeAttentionInvariant(observation_dim, 8, hidden_dim)
        self.mlp = _MLPBase(hidden_dim * 2, hidden_dim, layer_count=2)

    def forward(
        self,
        observations: torch.Tensor,
        neighbour_observations: torch.Tensor,
        neighbour_masks: torch.Tensor,
        neighbour_relations: torch.Tensor,
        neighbour_distances: torch.Tensor,
    ) -> torch.Tensor:
        neighbour_input = neighbour_observations[
            :, :, self.neighbour_feature_indices
        ]
        own, neighbour = self.invariant(
            observations,
            neighbour_input,
            neighbour_masks,
            neighbour_relations,
            neighbour_distances,
        )
        return self.mlp(torch.cat((own, neighbour), dim=-1))


class _CityLightActor(nn.Module):
    def __init__(self, observation_dim: int, action_dim: int):
        super().__init__()
        self.base = _CityLightBackbone(observation_dim)
        self.action_head = _init_linear(nn.Linear(64, action_dim), 0.01)

    def distribution(
        self,
        observations: torch.Tensor,
        available_actions: torch.Tensor,
        neighbour_observations: torch.Tensor,
        neighbour_masks: torch.Tensor,
        neighbour_relations: torch.Tensor,
        neighbour_distances: torch.Tensor,
    ) -> torch.distributions.Categorical:
        features = self.base(
            observations,
            neighbour_observations,
            neighbour_masks,
            neighbour_relations,
            neighbour_distances,
        )
        logits = self.action_head(features)
        logits = logits.masked_fill(available_actions == 0, -1e10)
        return torch.distributions.Categorical(logits=logits)


class _CityLightCritic(nn.Module):
    def __init__(self, observation_dim: int):
        super().__init__()
        self.base = _CityLightBackbone(observation_dim)
        self.value_head = _init_linear(nn.Linear(64, 1), 1.0)

    def forward(
        self,
        observations: torch.Tensor,
        neighbour_observations: torch.Tensor,
        neighbour_masks: torch.Tensor,
        neighbour_relations: torch.Tensor,
        neighbour_distances: torch.Tensor,
    ) -> torch.Tensor:
        return self.value_head(
            self.base(
                observations,
                neighbour_observations,
                neighbour_masks,
                neighbour_relations,
                neighbour_distances,
            )
        )


class _ValueNorm(nn.Module):
    """Official CityLight ValueNorm implementation."""

    def __init__(self, device: torch.device, beta: float = 0.99999):
        super().__init__()
        self.beta = beta
        self.epsilon = 1e-5
        self.register_buffer("running_mean", torch.zeros(1, device=device))
        self.register_buffer("running_mean_sq", torch.zeros(1, device=device))
        self.register_buffer("debiasing_term", torch.tensor(0.0, device=device))

    def running_mean_var(self) -> Tuple[torch.Tensor, torch.Tensor]:
        term = self.debiasing_term.clamp(min=self.epsilon)
        mean = self.running_mean / term
        mean_sq = self.running_mean_sq / term
        return mean, (mean_sq - mean.square()).clamp(min=1e-2)

    @torch.no_grad()
    def update(self, values: torch.Tensor) -> None:
        values = values.float()
        batch_mean = values.mean(dim=0)
        batch_sq_mean = values.square().mean(dim=0)
        self.running_mean.mul_(self.beta).add_(batch_mean * (1.0 - self.beta))
        self.running_mean_sq.mul_(self.beta).add_(
            batch_sq_mean * (1.0 - self.beta)
        )
        self.debiasing_term.mul_(self.beta).add_(1.0 - self.beta)

    def normalize(self, values: torch.Tensor) -> torch.Tensor:
        mean, variance = self.running_mean_var()
        return (values - mean) / torch.sqrt(variance)

    def denormalize_numpy(self, values: np.ndarray) -> np.ndarray:
        mean, variance = self.running_mean_var()
        tensor = torch.as_tensor(values, dtype=torch.float32, device=mean.device)
        return (tensor * torch.sqrt(variance) + mean).cpu().numpy()


class CityLightAgent(Agent):
    """Official CityLight observation/policy/MAPPO adapted only at SUMO I/O."""

    ROLLOUT_FILE = "citylight_rollout.pkl"

    def __init__(
        self,
        dic_agent_conf: Dict[str, Any],
        dic_traffic_env_conf: Dict[str, Any],
        dic_path: Dict[str, str],
        cnt_round: int,
        intersection_id: str = "0",
    ):
        super().__init__(
            dic_agent_conf, dic_traffic_env_conf, dic_path, intersection_id
        )
        self.num_actions = len(dic_traffic_env_conf["PHASE"])
        if self.num_actions != 4:
            raise ValueError(
                "Official CityLight supports heterogeneous 3/4-phase intersections "
                "through a four-action mask; --eightphase is not compatible."
            )
        self.observation_dim = self.num_actions * 3 + 1
        requested_device = str(dic_agent_conf.get("CITYLIGHT_DEVICE", "auto"))
        if requested_device == "auto":
            requested_device = (
                "cuda"
                if dic_agent_conf.get("CITYLIGHT_USE_CUDA", True)
                and torch.cuda.is_available()
                else "cpu"
            )
        self.device = torch.device(requested_device)

        seed = int(dic_agent_conf.get("CITYLIGHT_SEED", 1))
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

        self.actor = _CityLightActor(self.observation_dim, self.num_actions).to(
            self.device
        )
        self.critic = _CityLightCritic(self.observation_dim).to(self.device)
        learning_rate = float(dic_agent_conf.get("CITYLIGHT_LR", 5e-4))
        critic_learning_rate = float(
            dic_agent_conf.get("CITYLIGHT_CRITIC_LR", 5e-4)
        )
        optimizer_eps = float(dic_agent_conf.get("CITYLIGHT_OPT_EPS", 1e-5))
        weight_decay = float(dic_agent_conf.get("CITYLIGHT_WEIGHT_DECAY", 0.0))
        self.actor_optimizer = torch.optim.Adam(
            self.actor.parameters(),
            lr=learning_rate,
            eps=optimizer_eps,
            weight_decay=weight_decay,
        )
        self.critic_optimizer = torch.optim.Adam(
            self.critic.parameters(),
            lr=critic_learning_rate,
            eps=optimizer_eps,
            weight_decay=weight_decay,
        )
        self.value_normalizer = _ValueNorm(self.device)
        self._pending_step: Dict[str, np.ndarray] | None = None
        self._rollout_steps: list[Dict[str, np.ndarray]] = []
        self._last_next_inputs: Dict[str, np.ndarray] | None = None
        self.training_rollouts: list[Dict[str, Any]] = []

        if cnt_round > 0:
            previous = f"round_{cnt_round - 1}_inter_{intersection_id}"
            if os.path.isfile(self._checkpoint_path(previous)):
                self.load_network(previous)

        # Loading a checkpoint restores Adam moments and its old learning
        # rate.  Keep the moments for fine-tuning, then apply the smaller rate
        # requested by the current rolling window.
        for parameter_group in self.actor_optimizer.param_groups:
            parameter_group["lr"] = learning_rate
        for parameter_group in self.critic_optimizer.param_groups:
            parameter_group["lr"] = critic_learning_rate

        # All rollout workers load the same policy parameters, but must not
        # replay the same categorical samples/SUMO seed sequence.  The official
        # implementation keeps one long-lived RNG stream across episodes; the
        # repository pipeline creates one agent process per episode instead.
        rollout_seed = int(dic_agent_conf.get("CITYLIGHT_ROLLOUT_SEED", seed))
        random.seed(rollout_seed)
        np.random.seed(rollout_seed)
        torch.manual_seed(rollout_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(rollout_seed)

    def _checkpoint_path(self, file_name: str) -> str:
        suffix = "" if file_name.endswith(".pt") else ".pt"
        return os.path.join(self.dic_path["PATH_TO_MODEL"], file_name + suffix)

    @staticmethod
    def _required_state_array(
        state: Dict[str, Any], key: str, dtype: np.dtype
    ) -> np.ndarray:
        value = state.get(key)
        if value is None:
            raise KeyError(
                f"CityLight state is missing {key!r}; SUMO CityLight features "
                "must be initialized before policy inference."
            )
        return np.asarray(value, dtype=dtype)

    def _encode_states(self, states: Sequence[Dict[str, Any]]) -> Dict[str, np.ndarray]:
        observations = np.stack(
            [
                self._required_state_array(state, "citylight_observation", np.float32)
                for state in states
            ]
        )
        if observations.shape[1] != self.observation_dim:
            raise ValueError(
                f"Expected CityLight observation width {self.observation_dim}, "
                f"received {observations.shape[1]}"
            )
        available = np.stack(
            [
                self._required_state_array(
                    state, "citylight_available_actions", np.float32
                )
                for state in states
            ]
        )
        neighbour_indices = np.stack(
            [
                self._required_state_array(
                    state, "citylight_neighbor_indices", np.int64
                )
                for state in states
            ]
        )
        neighbour_masks = np.stack(
            [
                self._required_state_array(
                    state, "citylight_neighbor_mask", np.float32
                )
                for state in states
            ]
        )
        neighbour_relations = np.stack(
            [
                self._required_state_array(
                    state, "citylight_neighbor_relations", np.float32
                ).reshape(4, 2)
                for state in states
            ]
        )
        neighbour_distances = np.stack(
            [
                self._required_state_array(
                    state, "citylight_neighbor_distances", np.float32
                ).reshape(4, 2)
                for state in states
            ]
        )
        if neighbour_indices.shape[1] != 4:
            raise ValueError("CityLight requires exactly four aligned neighbour slots")
        safe_indices = np.clip(neighbour_indices, 0, max(len(states) - 1, 0))
        neighbour_observations = observations[safe_indices].copy()
        neighbour_observations[neighbour_masks == 0] = -1.0
        return {
            "observations": observations,
            "available_actions": available,
            "neighbour_indices": neighbour_indices,
            "neighbour_observations": neighbour_observations,
            "neighbour_masks": neighbour_masks,
            "neighbour_relations": neighbour_relations,
            "neighbour_distances": neighbour_distances,
            "local_queues": np.asarray(
                [float(state.get("citylight_local_queue", 0.0)) for state in states],
                dtype=np.float32,
            ),
        }

    def _tensor_inputs(self, inputs: Dict[str, np.ndarray]) -> Dict[str, torch.Tensor]:
        return {
            "observations": torch.as_tensor(
                inputs["observations"], dtype=torch.float32, device=self.device
            ),
            "available_actions": torch.as_tensor(
                inputs["available_actions"], dtype=torch.float32, device=self.device
            ),
            "neighbour_observations": torch.as_tensor(
                inputs["neighbour_observations"],
                dtype=torch.float32,
                device=self.device,
            ),
            "neighbour_masks": torch.as_tensor(
                inputs["neighbour_masks"], dtype=torch.float32, device=self.device
            ),
            "neighbour_relations": torch.as_tensor(
                inputs["neighbour_relations"],
                dtype=torch.float32,
                device=self.device,
            ),
            "neighbour_distances": torch.as_tensor(
                inputs["neighbour_distances"],
                dtype=torch.float32,
                device=self.device,
            ),
        }

    def choose_action(
        self, count: int, states: Sequence[Dict[str, Any]]
    ) -> np.ndarray:
        del count
        inputs = self._encode_states(states)
        tensors = self._tensor_inputs(inputs)
        deterministic = float(self.dic_agent_conf.get("EPSILON", 0.0)) <= 0
        self.actor.eval()
        self.critic.eval()
        with torch.no_grad():
            distribution = self.actor.distribution(**tensors)
            actions = (
                distribution.probs.argmax(dim=-1)
                if deterministic
                else distribution.sample()
            )
            log_probs = distribution.log_prob(actions).unsqueeze(-1)
            values = self.critic(
                tensors["observations"],
                tensors["neighbour_observations"],
                tensors["neighbour_masks"],
                tensors["neighbour_relations"],
                tensors["neighbour_distances"],
            )

        if not deterministic:
            self._pending_step = {
                **{key: value.copy() for key, value in inputs.items()},
                "actions": actions.cpu().numpy().reshape(-1, 1),
                "action_log_probs": log_probs.cpu().numpy(),
                "value_preds": values.cpu().numpy(),
            }
        return actions.cpu().numpy()

    def record_transition(
        self, next_states: Sequence[Dict[str, Any]], done: bool
    ) -> np.ndarray | None:
        if self._pending_step is None:
            return None
        next_inputs = self._encode_states(next_states)
        rewards = -next_inputs["local_queues"].copy()
        alpha = float(
            self.dic_agent_conf.get("CITYLIGHT_NEIGHBOUR_REWARD_ALPHA", 0.2)
        )
        if alpha:
            neighbour_rewards = np.zeros_like(rewards)
            indices = self._pending_step["neighbour_indices"]
            masks = self._pending_step["neighbour_masks"]
            for node in range(len(rewards)):
                valid = indices[node][masks[node] > 0]
                if valid.size:
                    neighbour_rewards[node] = rewards[valid].mean()
            rewards = rewards + alpha * neighbour_rewards

        step = dict(self._pending_step)
        step["rewards"] = rewards.reshape(-1, 1)
        step["next_mask"] = np.full(
            (len(rewards), 1), 0.0 if done else 1.0, dtype=np.float32
        )
        self._rollout_steps.append(step)
        self._last_next_inputs = next_inputs
        self._pending_step = None
        return rewards.copy()

    def save_rollout(self, directory: str) -> str | None:
        if not self._rollout_steps or self._last_next_inputs is None:
            return None
        tensors = self._tensor_inputs(self._last_next_inputs)
        self.critic.eval()
        with torch.no_grad():
            next_value = self.critic(
                tensors["observations"],
                tensors["neighbour_observations"],
                tensors["neighbour_masks"],
                tensors["neighbour_relations"],
                tensors["neighbour_distances"],
            ).cpu().numpy()
        payload = {
            "steps": self._rollout_steps,
            "next_value": next_value,
        }
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, self.ROLLOUT_FILE)
        with open(path, "wb") as file_obj:
            pickle.dump(payload, file_obj, protocol=pickle.HIGHEST_PROTOCOL)
        return path

    def prepare_Xs_Y(self, memory: Sequence[Any]) -> None:
        self.training_rollouts = [
            rollout
            for rollout in memory
            if isinstance(rollout, dict) and rollout.get("steps")
        ]

    @staticmethod
    def _huber_loss(error: torch.Tensor, delta: float) -> torch.Tensor:
        absolute = error.abs()
        return torch.where(
            absolute <= delta,
            error.square() / 2,
            delta * (absolute - delta / 2),
        )

    def _value_loss(
        self,
        values: torch.Tensor,
        old_values: torch.Tensor,
        returns: torch.Tensor,
        clip_param: float,
    ) -> torch.Tensor:
        clipped_values = old_values + (values - old_values).clamp(
            -clip_param, clip_param
        )
        self.value_normalizer.update(returns)
        normalized_returns = self.value_normalizer.normalize(returns)
        original_error = normalized_returns - values
        clipped_error = normalized_returns - clipped_values
        original_loss = self._huber_loss(original_error, 10.0)
        clipped_loss = self._huber_loss(clipped_error, 10.0)
        return torch.maximum(original_loss, clipped_loss).mean()

    @staticmethod
    def _concatenate_steps(
        rollouts: Iterable[Dict[str, Any]], key: str
    ) -> np.ndarray:
        return np.concatenate(
            [np.stack([step[key] for step in rollout["steps"]]) for rollout in rollouts],
            axis=0,
        )

    def train_network(self) -> None:
        if not self.training_rollouts:
            print("CityLight: no on-policy rollouts available; skipping update")
            return

        gamma = float(self.dic_agent_conf.get("GAMMA", 0.99))
        gae_lambda = float(self.dic_agent_conf.get("CITYLIGHT_GAE_LAMBDA", 0.95))
        rollout_returns = []
        rollout_advantages = []
        for rollout in self.training_rollouts:
            rewards = np.stack([step["rewards"] for step in rollout["steps"]])
            values = np.stack([step["value_preds"] for step in rollout["steps"]])
            masks = np.stack([step["next_mask"] for step in rollout["steps"]])
            value_sequence = np.concatenate(
                (values, np.asarray(rollout["next_value"])[None]), axis=0
            )
            denormalized_values = self.value_normalizer.denormalize_numpy(
                value_sequence
            )
            returns = np.zeros_like(values)
            gae = np.zeros_like(values[0])
            for step_index in reversed(range(len(rewards))):
                delta = (
                    rewards[step_index]
                    + gamma
                    * denormalized_values[step_index + 1]
                    * masks[step_index]
                    - denormalized_values[step_index]
                )
                gae = (
                    delta
                    + gamma * gae_lambda * masks[step_index] * gae
                )
                returns[step_index] = gae + denormalized_values[step_index]
            rollout_returns.append(returns)
            rollout_advantages.append(returns - denormalized_values[:-1])

        arrays = {
            key: self._concatenate_steps(self.training_rollouts, key)
            for key in (
                "observations",
                "available_actions",
                "neighbour_observations",
                "neighbour_masks",
                "neighbour_relations",
                "neighbour_distances",
                "actions",
                "action_log_probs",
                "value_preds",
            )
        }
        arrays["returns"] = np.concatenate(rollout_returns, axis=0)
        advantages = np.concatenate(rollout_advantages, axis=0)
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-5)
        arrays["advantages"] = advantages

        def flatten(value: np.ndarray) -> np.ndarray:
            return value.reshape(-1, *value.shape[2:])

        batch = {
            key: torch.as_tensor(flatten(value), device=self.device)
            for key, value in arrays.items()
        }
        batch_size = batch["observations"].shape[0]
        num_mini_batches = int(
            self.dic_agent_conf.get("CITYLIGHT_NUM_MINI_BATCH", 18)
        )
        num_mini_batches = max(1, min(num_mini_batches, batch_size))
        mini_batch_size = batch_size // num_mini_batches
        ppo_epochs = int(self.dic_agent_conf.get("CITYLIGHT_PPO_EPOCHS", 10))
        configured_steps = self.dic_agent_conf.get("FINE_TUNE_STEPS")
        max_update_steps = (
            int(configured_steps) if configured_steps is not None else None
        )
        clip_param = float(self.dic_agent_conf.get("CITYLIGHT_CLIP_PARAM", 0.2))
        entropy_coef = float(
            self.dic_agent_conf.get("CITYLIGHT_ENTROPY_COEF", 0.01)
        )
        value_coef = float(
            self.dic_agent_conf.get("CITYLIGHT_VALUE_LOSS_COEF", 1.0)
        )
        max_grad_norm = float(
            self.dic_agent_conf.get("CITYLIGHT_MAX_GRAD_NORM", 10.0)
        )

        self.actor.train()
        self.critic.train()
        final_policy_loss = final_value_loss = float("nan")
        update_steps = 0
        for _ in range(ppo_epochs):
            permutation = torch.randperm(batch_size, device=self.device)
            for mini_batch in range(num_mini_batches):
                start = mini_batch * mini_batch_size
                indices = permutation[start : start + mini_batch_size]
                if indices.numel() == 0:
                    continue
                common = {
                    "observations": batch["observations"][indices].float(),
                    "neighbour_observations": batch["neighbour_observations"][indices].float(),
                    "neighbour_masks": batch["neighbour_masks"][indices].float(),
                    "neighbour_relations": batch["neighbour_relations"][indices].float(),
                    "neighbour_distances": batch["neighbour_distances"][indices].float(),
                }
                distribution = self.actor.distribution(
                    available_actions=batch["available_actions"][indices].float(),
                    **common,
                )
                action_log_probs = distribution.log_prob(
                    batch["actions"][indices].long().squeeze(-1)
                ).unsqueeze(-1)
                ratio = torch.exp(
                    action_log_probs
                    - batch["action_log_probs"][indices].float()
                )
                advantages_batch = batch["advantages"][indices].float()
                surrogate_one = ratio * advantages_batch
                surrogate_two = ratio.clamp(
                    1.0 - clip_param, 1.0 + clip_param
                ) * advantages_batch
                policy_loss = -torch.minimum(
                    surrogate_one, surrogate_two
                ).sum(dim=-1, keepdim=True).mean()
                entropy = distribution.entropy().mean()

                self.actor_optimizer.zero_grad(set_to_none=True)
                (policy_loss - entropy_coef * entropy).backward()
                nn.utils.clip_grad_norm_(self.actor.parameters(), max_grad_norm)
                self.actor_optimizer.step()

                values = self.critic(**common)
                value_loss = self._value_loss(
                    values,
                    batch["value_preds"][indices].float(),
                    batch["returns"][indices].float(),
                    clip_param,
                )
                self.critic_optimizer.zero_grad(set_to_none=True)
                (value_loss * value_coef).backward()
                nn.utils.clip_grad_norm_(self.critic.parameters(), max_grad_norm)
                self.critic_optimizer.step()
                final_policy_loss = float(policy_loss.detach().cpu())
                final_value_loss = float(value_loss.detach().cpu())
                update_steps += 1
                if (
                    max_update_steps is not None
                    and update_steps >= max_update_steps
                ):
                    break
            if (
                max_update_steps is not None
                and update_steps >= max_update_steps
            ):
                break

        print(
            "CityLight MAPPO update finished, "
            f"policy_loss={final_policy_loss:.6f}, "
            f"value_loss={final_value_loss:.6f}, samples={batch_size}, "
            f"updates={update_steps}"
        )

    def save_network(self, file_name: str) -> None:
        os.makedirs(self.dic_path["PATH_TO_MODEL"], exist_ok=True)
        torch.save(
            {
                "actor": self.actor.state_dict(),
                "critic": self.critic.state_dict(),
                "actor_optimizer": self.actor_optimizer.state_dict(),
                "critic_optimizer": self.critic_optimizer.state_dict(),
                "value_normalizer": self.value_normalizer.state_dict(),
                "num_actions": self.num_actions,
                "observation_dim": self.observation_dim,
            },
            self._checkpoint_path(file_name),
        )

    def load_network(self, file_name: str, file_path: str | None = None) -> None:
        if file_path is None:
            checkpoint_path = self._checkpoint_path(file_name)
        else:
            suffix = "" if file_name.endswith(".pt") else ".pt"
            checkpoint_path = os.path.join(file_path, file_name + suffix)
        try:
            checkpoint = torch.load(
                checkpoint_path, map_location=self.device, weights_only=False
            )
        except TypeError:
            checkpoint = torch.load(checkpoint_path, map_location=self.device)
        self.actor.load_state_dict(checkpoint["actor"])
        self.critic.load_state_dict(checkpoint["critic"])
        if "actor_optimizer" in checkpoint:
            self.actor_optimizer.load_state_dict(checkpoint["actor_optimizer"])
        if "critic_optimizer" in checkpoint:
            self.critic_optimizer.load_state_dict(checkpoint["critic_optimizer"])
        if "value_normalizer" in checkpoint:
            self.value_normalizer.load_state_dict(checkpoint["value_normalizer"])
        print(f"succeed in loading CityLight model {checkpoint_path}")
