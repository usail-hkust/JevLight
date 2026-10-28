"""RL rollout generator.

One ``Generator`` per round resets the SUMO environment, steps it at the
control interval while the single shared agent picks canonical actions for
the whole network, records training metrics, and saves the on-policy rollout
for CityLight.
"""

from baselines.rl.rl_config import DIC_AGENTS
from utils.sumo_env import SUMOEnv
import time
import os
import copy
import numpy as np
from tqdm import tqdm


class Generator:
    def __init__(self, cnt_round, cnt_gen, dic_path, dic_agent_conf, dic_traffic_env_conf):

        self.cnt_round = cnt_round
        self.cnt_gen = cnt_gen
        self.dic_path = dic_path
        self.dic_agent_conf = copy.deepcopy(dic_agent_conf)
        self.dic_traffic_env_conf = dic_traffic_env_conf
        if self.dic_traffic_env_conf["MODEL_NAME"] == "CityLight":
            base_seed = int(self.dic_agent_conf.get("CITYLIGHT_SEED", 1))
            generator_count = int(self.dic_traffic_env_conf["NUM_GENERATORS"])
            self.dic_agent_conf["CITYLIGHT_ROLLOUT_SEED"] = (
                base_seed + self.cnt_round * generator_count + self.cnt_gen
            )
        self.agents = [None]*dic_traffic_env_conf['NUM_AGENTS']
        self.path_to_log = os.path.join(self.dic_path["PATH_TO_WORK_DIRECTORY"], "train_round",
                                        "round_"+str(self.cnt_round), "generator_"+str(self.cnt_gen))
        if not os.path.exists(self.path_to_log):
            os.makedirs(self.path_to_log)
            start_time = time.time()
            for i in range(dic_traffic_env_conf['NUM_AGENTS']):
                agent_name = self.dic_traffic_env_conf["MODEL_NAME"]
                agent = DIC_AGENTS[agent_name](
                    dic_agent_conf=self.dic_agent_conf,
                    dic_traffic_env_conf=self.dic_traffic_env_conf,
                    dic_path=self.dic_path,
                    cnt_round=self.cnt_round,
                    intersection_id=str(i)
                )
                self.agents[i] = agent
            print("Create intersection agent time: ", time.time()-start_time)

        self.env = SUMOEnv(
            path_to_log=self.path_to_log,
            path_to_work_directory=self.dic_path["PATH_TO_WORK_DIRECTORY"],
            dic_traffic_env_conf=self.dic_traffic_env_conf,
            dic_path=dic_path
        )

    def generate(self, logger=None):

        reset_env_start_time = time.time()
        done = False
        training_start_time = int(
            self.dic_traffic_env_conf.get("TRAIN_START_TIME", 0) or 0
        )
        if training_start_time > 0:
            self.env._start_time = training_start_time
        state = self.env.reset()
        reset_env_time = time.time() - reset_env_start_time
        running_start_time = time.time()

        # Initialize training metrics
        training_metrics = {
            'total_reward': 0.0,
            'queue_length_episode': [],
            'waiting_time_episode': [],
            'global_waiting_times': []
        }

        # Track overall results for periodic logging
        overall_results = {
            "avg_travel_time": [],
            "avg_queue_len": [],
            "avg_waiting_time": []
        }

        total_run_cnt = self.dic_traffic_env_conf["RUN_COUNTS"]
        training_end_time = training_start_time + total_run_cnt
        results = {}  # Initialize results variable
        control_interval = self.dic_traffic_env_conf["MIN_ACTION_TIME"]
        current_time = self.env.get_current_time()

        step_num = 0
        with tqdm(total=total_run_cnt, desc="Simulation Progress", unit="s") as pbar:
            while not done and current_time < training_end_time:
                current_time = self.env.get_current_time()
                step_start_time = time.time()
                all_indices = list(range(len(self.env.list_intersection)))
                action_list = self._get_due_actions(
                    state,
                    step_num,
                    all_indices,
                )
                step_duration = min(
                    control_interval,
                    int(training_end_time - current_time),
                )
                next_state, reward, done, _ = self.env.step(
                    action_list,
                    min_action_time=step_duration,
                )

                metric_reward = reward
                if self.dic_traffic_env_conf["MODEL_NAME"] == "CityLight":
                    terminal = done or self.env.get_current_time() >= total_run_cnt
                    citylight_reward = self.agents[0].record_transition(
                        next_state, terminal
                    )
                    if citylight_reward is not None:
                        # record_transition returns (N, 1); training metrics
                        # expect a flat per-intersection reward list.
                        metric_reward = citylight_reward.reshape(-1).tolist()

                print("time: {0}, step: {1}, running_time: {2}".format(
                    current_time,
                    step_duration,
                    time.time()-step_start_time,
                ))
                # Update training metrics
                self._update_training_metrics(training_metrics, metric_reward)

                # Get current time
                current_time = self.env.get_current_time()

                # Keep periodic summaries for console output. Wandb logging is done
                # by Pipeline after the full generator rollout finishes so every
                # training round produces exactly one train/* point.
                if current_time % 3600 == 0:
                    results = self._calculate_final_results(training_metrics)
                    overall_results["avg_travel_time"].append(results["avg_travel_time"])
                    overall_results["avg_queue_len"].append(results["avg_queue_len"])
                    overall_results["avg_waiting_time"].append(results["avg_waiting_time"])

                state = next_state
                step_num += 1
                pbar.update(step_duration)

        running_time = time.time() - running_start_time
        log_start_time = time.time()
        print("start logging.......................")

        if self.dic_traffic_env_conf["MODEL_NAME"] == "CityLight":
            rollout_path = self.agents[0].save_rollout(self.path_to_log)
            if rollout_path is None:
                raise RuntimeError("CityLight generator produced no on-policy rollout")
            print(f"CityLight rollout saved to {rollout_path}")

        # Calculate final results
        results = self._calculate_final_results(training_metrics)

        # Log final results
        print(f"============== End Training ==============")
        print(f"Average Travel Time: {np.mean(overall_results['avg_travel_time']) if overall_results['avg_travel_time'] else results['avg_travel_time']}\n"
              f"Average Queue Length: {np.mean(overall_results['avg_queue_len']) if overall_results['avg_queue_len'] else results['avg_queue_len']}\n"
              f"Average Waiting Time: {np.mean(overall_results['avg_waiting_time']) if overall_results['avg_waiting_time'] else results['avg_waiting_time']}")

        self.env.bulk_log_multi_process()
        log_time = time.time() - log_start_time
        self.env.end_engine()
        print("reset_env_time: ", reset_env_time)
        print("running_time: ", running_time)
        print("log_time: ", log_time)

        return results

    def _is_graph_model(self):
        return self.dic_traffic_env_conf["MODEL_NAME"] in [
            "EfficientPressLight", "EfficientColight", "EfficientMPLight",
            "Attend", "Colight", "MPLight", "AdvancedMPLight",
            "AdvancedColight", "AdvancedDQN",
            "CityLight",
        ]

    def _map_action_for_intersection(self, intersection_idx, action):
        local_action_map = self.env.list_intersection[intersection_idx]._get_four_phase()[0]
        if not local_action_map:
            return 0
        if self.dic_traffic_env_conf["MODEL_NAME"] == "CityLight":
            canonical_action = int(action)
            if canonical_action in local_action_map:
                return local_action_map[canonical_action]
            return local_action_map[min(local_action_map)]
        canonical_action = int(action) % len(local_action_map)
        return local_action_map.get(canonical_action, canonical_action)

    def _get_due_actions(self, state, step_num, due_indices):
        action_list = {}
        if not due_indices:
            return action_list

        if self._is_graph_model():
            actions = self.agents[0].choose_action(step_num, state)
            for idx in due_indices:
                inter = self.env.list_intersection[idx]
                action_list[inter.inter_id] = self._map_action_for_intersection(idx, actions[idx])
            return action_list

        for idx in due_indices:
            inter = self.env.list_intersection[idx]
            action = self.agents[idx].choose_action(step_num, state[idx])
            action_list[inter.inter_id] = self._map_action_for_intersection(idx, action)
        return action_list

    def _update_training_metrics(self, metrics, reward) -> None:
        """Update training metrics with current step data."""
        metrics['total_reward'] += sum(reward)

        queue_lengths = []
        for intersection in self.env.list_intersection:
            queue_length = sum(intersection.dic_feature.get('lane_num_waiting_vehicle_in', [0]))
            queue_lengths.append(queue_length)
        metrics['queue_length_episode'].append(sum(queue_lengths))

        # waiting_vehicle_list is now managed by SUMOEnv directly
        waiting_times = [
            time_info for v_id, time_info in self.env.waiting_vehicle_list.items()
        ]
        avg_waiting_time = np.mean(waiting_times) if waiting_times else 0.0
        metrics['waiting_time_episode'].append(avg_waiting_time)
        metrics['global_waiting_times'].extend(waiting_times)

    def _calculate_final_results(self, metrics):
        """Calculate final training results using the same env aggregates as test."""
        vehicle_travel_times = self.env.get_all_vehicle_travel_times()
        arrived_travel_times = self.env.get_arrived_vehicle_travel_times()
        waiting_times = self.env.get_all_vehicle_waiting_times()
        queue_totals = self.env.get_intersection_queue_totals()
        queue_step_count = queue_totals.get("step_count", 0)

        avg_travel_time = (
            float(np.mean(list(vehicle_travel_times.values())))
            if vehicle_travel_times
            else 0.0
        )
        avg_waiting_time = (
            float(np.mean(list(waiting_times.values())))
            if waiting_times
            else 0.0
        )
        avg_queue_len = (
            queue_totals["sum"] / queue_step_count
            if queue_step_count
            else 0.0
        )
        queuing_vehicle_num = queue_totals.get("sum", 0.0)

        return {
            "training_reward": metrics['total_reward'],
            "avg_queue_len": avg_queue_len,
            "queuing_vehicle_num": queuing_vehicle_num,
            "training_queuing_vehicle_num": queuing_vehicle_num,
            "avg_waiting_time": avg_waiting_time,
            "avg_travel_time": avg_travel_time,
            "vehicle_count": len(vehicle_travel_times),
            "arrived_vehicle_count": len(arrived_travel_times),
            "observed_vehicle_count": len(waiting_times),
            "intersection_observation_count": int(
                queue_totals.get("count", 0)
            ),
            "queue_observation_step_count": int(queue_step_count),
        }
