"""Per-round and final checkpoint evaluation during RL training.

Implementation notes: the state-action logging is dropped, ``test`` returns
only the results dict, the work directory is an explicit ``work_dir``
parameter, and the agent.conf is additionally read from the model directory
where the pipeline writes it at the end of training.
"""

from baselines.rl.rl_config import DIC_AGENTS
from copy import deepcopy
from utils.sumo_env import SUMOEnv
import json
import os
import numpy as np
from tqdm import tqdm
from jevlight.wandb_utils import safe_wandb_log


def _is_graph_model(model_name):
    return model_name in [
        "EfficientPressLight", "EfficientColight", "EfficientMPLight",
        "AdvancedMPLight", "AdvancedColight", "AdvancedDQN", "Attend",
        "PressLight", "MPLight", "DQN", "Colight",
        "CityLight",
    ]


def _map_action_for_intersection(env, intersection_idx, action, model_name=None):
    local_action_map = env.list_intersection[intersection_idx]._get_four_phase()[0]
    if not local_action_map:
        return 0
    if model_name == "CityLight":
        canonical_action = int(action)
        if canonical_action in local_action_map:
            return local_action_map[canonical_action]
        return local_action_map[min(local_action_map)]
    canonical_action = int(action) % len(local_action_map)
    return local_action_map.get(canonical_action, canonical_action)


def _get_due_actions(env, agents, dic_traffic_env_conf, state, step_num, due_indices):
    action_list = {}
    if not due_indices:
        return action_list

    model_name = dic_traffic_env_conf["MODEL_NAME"]
    if _is_graph_model(model_name):
        actions = agents[0].choose_action(step_num, state)
        for idx in due_indices:
            inter = env.list_intersection[idx]
            action_list[inter.inter_id] = _map_action_for_intersection(
                env, idx, actions[idx], model_name
            )
        return action_list

    for idx in due_indices:
        inter = env.list_intersection[idx]
        action = agents[idx].choose_action(step_num, state[idx])
        action_list[inter.inter_id] = _map_action_for_intersection(
            env, idx, action, model_name
        )
    return action_list


def test(
    model_dir,
    data_dir,
    cnt_round,
    run_cnt,
    _dic_traffic_env_conf,
    logger=None,
    start_time=0,
    evaluation_name="test",
    checkpoint_interval=0,
    work_dir=None,
):
    dic_traffic_env_conf = deepcopy(_dic_traffic_env_conf)
    records_dir = (
        work_dir if work_dir is not None else model_dir.replace("model", "records")
    )
    model_round = "round_%d" % cnt_round
    dic_path = {"PATH_TO_DATA": data_dir, "PATH_TO_MODEL": model_dir, "PATH_TO_WORK_DIRECTORY": records_dir}
    # copy_conf_file writes agent.conf into both the work directory and the
    # model directory; prefer the work directory, fall back to the model one.
    agent_conf_path = os.path.join(records_dir, "agent.conf")
    if not os.path.exists(agent_conf_path):
        agent_conf_path = os.path.join(model_dir, "agent.conf")
    with open(agent_conf_path, "r") as f:
        dic_agent_conf = json.load(f)
    if os.path.exists(os.path.join(records_dir, "anon_env.conf")):
        with open(os.path.join(records_dir, "anon_env.conf"), "r") as f:
            dic_traffic_env_conf = json.load(f)
    dic_traffic_env_conf["RUN_COUNTS"] = run_cnt

    if dic_traffic_env_conf["MODEL_NAME"] in dic_traffic_env_conf["LIST_MODEL_NEED_TO_UPDATE"]:
        dic_agent_conf["EPSILON"] = 0
        dic_agent_conf["MIN_EPSILON"] = 0

    agents = []
    for i in range(dic_traffic_env_conf['NUM_AGENTS']):
        agent_name = dic_traffic_env_conf["MODEL_NAME"]
        agent = DIC_AGENTS[agent_name](
            dic_agent_conf=dic_agent_conf,
            dic_traffic_env_conf=dic_traffic_env_conf,
            dic_path=dic_path,
            cnt_round=0,
            intersection_id=str(i)
        )
        agents.append(agent)
    try:
        for i in range(dic_traffic_env_conf['NUM_AGENTS']):
            agents[i].load_network("{0}_inter_{1}".format(model_round, agents[i].intersection_id))
        path_to_log = os.path.join(
            dic_path["PATH_TO_WORK_DIRECTORY"],
            f"{evaluation_name}_round",
            model_round,
        )
        if not os.path.exists(path_to_log):
            os.makedirs(path_to_log)
        env = SUMOEnv(
            path_to_log=path_to_log,
            path_to_work_directory=dic_path["PATH_TO_WORK_DIRECTORY"],
            dic_traffic_env_conf=dic_traffic_env_conf,
            dic_path=dic_path
        )

        done = False

        total_time = dic_traffic_env_conf["RUN_COUNTS"]
        test_start_time = int(start_time or 0)
        if test_start_time > 0:
            env._start_time = test_start_time
        state = env.reset()
        if test_start_time > 0 and hasattr(env, "start_travel_time_measurement"):
            env.start_travel_time_measurement(test_start_time)

        # Initialize test metrics
        test_metrics = {
            'total_reward': 0.0,
            'queue_length_episode': [],
            'waiting_time_episode': [],
            'global_waiting_times': []
        }
        checkpoint_metrics = {
            'total_reward': 0.0,
            'queue_length_episode': [],
            'waiting_time_episode': [],
            'global_waiting_times': [],
        }

        test_end_time = test_start_time + total_time
        checkpoint_idx = 0
        checkpoint_start_time = test_start_time
        next_checkpoint_time = (
            min(test_end_time, test_start_time + int(checkpoint_interval))
            if checkpoint_interval
            else None
        )

        green_time = env.get_green_time()
        current_time = env.get_current_time()
        next_decision_time = {
            inter.inter_id: current_time
            for inter in env.list_intersection
        }

        step_num = 0
        with tqdm(total=total_time, desc="Test Progress", unit="s") as pbar:
            while not done and current_time < test_end_time:
                current_time = env.get_current_time()
                due_indices = [
                    idx
                    for idx, inter in enumerate(env.list_intersection)
                    if current_time >= next_decision_time[inter.inter_id] - 0.5
                ]
                action_list = _get_due_actions(
                    env, agents, dic_traffic_env_conf, state, step_num, due_indices
                )
                for idx in due_indices:
                    inter = env.list_intersection[idx]
                    if inter.inter_id not in action_list:
                        continue
                    next_decision_time[inter.inter_id] = current_time + green_time

                event_times = [test_end_time] + list(next_decision_time.values())
                if next_checkpoint_time is not None:
                    event_times.append(next_checkpoint_time)
                next_event_time = min(event_times)
                step_duration = max(1, int(min(next_event_time, test_end_time) - current_time))
                next_state, reward, done, _ = env.step(
                    action_list,
                    min_action_time=step_duration,
                )

                state = next_state

                # Update test metrics
                _update_test_metrics(test_metrics, reward, env)
                if checkpoint_interval:
                    _update_test_metrics(checkpoint_metrics, reward, env)

                # Get current time
                current_time = env.get_current_time()
                if (
                    next_checkpoint_time is not None
                    and current_time >= next_checkpoint_time
                ):
                    _log_checkpoint_results(
                        logger,
                        evaluation_name,
                        checkpoint_idx,
                        checkpoint_start_time,
                        next_checkpoint_time,
                        checkpoint_metrics,
                        env,
                    )
                    checkpoint_idx += 1
                    checkpoint_start_time = next_checkpoint_time
                    checkpoint_metrics = {
                        'total_reward': 0.0,
                        'queue_length_episode': [],
                        'waiting_time_episode': [],
                        'global_waiting_times': [],
                    }
                    next_checkpoint_time = min(
                        test_end_time,
                        next_checkpoint_time + int(checkpoint_interval),
                    )
                    if current_time >= test_end_time:
                        next_checkpoint_time = None

                step_num += 1
                pbar.update(step_duration)

        if (
            checkpoint_interval
            and checkpoint_metrics["queue_length_episode"]
        ):
            _log_checkpoint_results(
                logger,
                evaluation_name,
                checkpoint_idx,
                checkpoint_start_time,
                current_time,
                checkpoint_metrics,
                env,
            )

        results = _calculate_full_test_results(test_metrics, env)
        print(f"============== End Testing ==============")
        print(f"Average Travel Time: {results['test_avg_travel_time_over']}\n"
              f"Average Queue Length: {results['test_avg_queue_len_over']}\n"
              f"Average Waiting Time: {results['test_avg_waiting_time_over']}")

        env.end_engine()
        return results

    except Exception as e:
        print(e)
        print("============== error occurs in model_test ============")

        return None


def _update_test_metrics(metrics, reward, env):
    """Update test metrics with current step data."""
    metrics['total_reward'] += sum(reward)

    queue_lengths = []
    for intersection in env.list_intersection:
        queue_length = sum(intersection.dic_feature.get('lane_num_waiting_vehicle_in', [0]))
        queue_lengths.append(queue_length)
    metrics['queue_length_episode'].append(sum(queue_lengths))

    # waiting_vehicle_list is now managed by SUMOEnv directly
    waiting_times = [
        time_info for v_id, time_info in env.waiting_vehicle_list.items()
    ]
    avg_waiting_time = np.mean(waiting_times) if waiting_times else 0.0
    metrics['waiting_time_episode'].append(avg_waiting_time)
    metrics['global_waiting_times'].extend(waiting_times)


def _calculate_full_test_results(metrics, env):
    """Calculate one metric set over the complete test simulation."""
    vehicle_travel_times = env.get_all_vehicle_travel_times()
    arrived_travel_times = env.get_arrived_vehicle_travel_times()
    waiting_times = env.get_all_vehicle_waiting_times()
    queue_totals = env.get_intersection_queue_totals()
    queue_step_count = queue_totals.get("step_count", 0)
    return {
        "test_reward_over": metrics["total_reward"],
        "test_avg_queue_len_over": (
            queue_totals["sum"] / queue_step_count
            if queue_step_count
            else 0.0
        ),
        "test_queuing_vehicle_num_over": queue_totals.get("sum", 0.0),
        "test_avg_waiting_time_over": (
            float(np.mean(list(waiting_times.values())))
            if waiting_times
            else 0.0
        ),
        "test_avg_travel_time_over": (
            float(np.mean(list(vehicle_travel_times.values())))
            if vehicle_travel_times
            else 0.0
        ),
        "test_vehicle_count": len(vehicle_travel_times),
        "test_arrived_vehicle_count": len(arrived_travel_times),
        "test_observed_vehicle_count": len(waiting_times),
        "test_intersection_observation_count": int(
            queue_totals.get("count", 0)
        ),
        "test_queue_observation_step_count": int(queue_step_count),
    }


def _log_checkpoint_results(
    logger,
    namespace,
    checkpoint_idx,
    checkpoint_start_time,
    checkpoint_end_time,
    metrics,
    env,
):
    """Log one final checkpoint with segment and cumulative metrics."""
    if logger is None:
        return

    cumulative = _calculate_full_test_results(metrics, env)
    safe_wandb_log(logger, {
        f"{namespace}/checkpoint": checkpoint_idx,
        f"{namespace}/start_time": checkpoint_start_time,
        f"{namespace}/end_time": checkpoint_end_time,
        f"{namespace}/duration": (
            checkpoint_end_time - checkpoint_start_time
        ),
        f"{namespace}/reward": metrics["total_reward"],
        f"{namespace}/avg_queue_len": cumulative[
            "test_avg_queue_len_over"
        ],
        f"{namespace}/queuing_vehicle_num": cumulative[
            "test_queuing_vehicle_num_over"
        ],
        f"{namespace}/avg_waiting_time": cumulative[
            "test_avg_waiting_time_over"
        ],
        f"{namespace}/avg_travel_time": cumulative[
            "test_avg_travel_time_over"
        ],
        f"{namespace}/vehicle_count": cumulative["test_vehicle_count"],
        f"{namespace}/arrived_vehicle_count": cumulative[
            "test_arrived_vehicle_count"
        ],
        f"{namespace}/observed_vehicle_count": cumulative[
            "test_observed_vehicle_count"
        ],
        f"{namespace}/intersection_observation_count": cumulative[
            "test_intersection_observation_count"
        ],
        f"{namespace}/queue_observation_step_count": cumulative[
            "test_queue_observation_step_count"
        ],
    })
