import numpy as np
import pickle
import os
import traceback


def get_reward_from_features(rs):
    reward = {"queue_length": np.sum(rs["lane_num_waiting_vehicle_in"]),
              "pressure": np.absolute(np.sum(rs["pressure"]))}
    return reward


def cal_reward(rs, rewards_components):
    r = 0
    for component, weight in rewards_components.items():
        if weight == 0:
            continue
        if component not in rs.keys():
            continue
        if rs[component] is None:
            continue
        r += rs[component] * weight
    return r


class ConstructSample:

    def __init__(self, path_to_samples, cnt_round, dic_traffic_env_conf):
        self.parent_dir = path_to_samples
        self.path_to_samples = path_to_samples + "/round_" + str(cnt_round)
        self.cnt_round = cnt_round
        self.dic_traffic_env_conf = dic_traffic_env_conf

        self.logging_data_list_per_gen = None
        self.hidden_states_list = None
        self.samples = []
        self.samples_all_intersection = [None]*self.dic_traffic_env_conf['NUM_INTERSECTIONS']

        self.interval = self.dic_traffic_env_conf["MIN_ACTION_TIME"]
        self.measure_time = self.dic_traffic_env_conf["MEASURE_TIME"]
        self.reward_aggregation = self.dic_traffic_env_conf.get(
            "REWARD_AGGREGATION",
            "average",
        )

    def load_data(self, folder, i):
        try:
            f_logging_data = open(os.path.join(self.path_to_samples, folder, "inter_{0}.pkl".format(i)), "rb")
            logging_data = pickle.load(f_logging_data)
            f_logging_data.close()
            # Rolling training windows start SUMO at an absolute timestamp.
            # ConstructSample historically assumes the first entry is t=1 and
            # indexes the list with ``time - 1``.  Normalize only the in-memory
            # timestamps so the same sampler works for every 3-hour slice.
            if logging_data:
                first_time = int(logging_data[0].get("time", 1))
                time_offset = first_time - 1
                if time_offset:
                    for item in logging_data:
                        item["time"] = int(item.get("time", 0)) - time_offset
            return 1, logging_data

        except Exception:
            print("Error occurs when making samples for inter {0}".format(i))
            print('traceback.format_exc():\n%s' % traceback.format_exc())
            return 0, None

    def load_data_for_system(self, folder):
        self.logging_data_list_per_gen = []
        print("Load data for system in ", folder)
        for i in range(self.dic_traffic_env_conf['NUM_INTERSECTIONS']):
            pass_code, logging_data = self.load_data(folder, i)
            if pass_code == 0:
                return 0
            self.logging_data_list_per_gen.append(logging_data)
        return 1

    def construct_state(self, features, time, i):
        state = self.logging_data_list_per_gen[i][time - 1]
        assert time == state["time"]
        if self.dic_traffic_env_conf["BINARY_PHASE_EXPANSION"]:
            state_after_selection = {}
            for key, value in state["state"].items():
                if key in features:
                    if "cur_phase" in key:
                        state_after_selection[key] = self.dic_traffic_env_conf['PHASE'][value[0]]
                    else:
                        state_after_selection[key] = value
        else:
            state_after_selection = {key: value for key, value in state["state"].items() if key in features}
        return state_after_selection

    def construct_reward(self, rewards_components, time, i):
        reward_time = time + self.measure_time
        rs = self.logging_data_list_per_gen[i][reward_time - 1]
        assert reward_time == rs["time"]
        rs = get_reward_from_features(rs['state'])
        r_instant = cal_reward(rs, rewards_components)
        # average
        list_r = []
        for t in range(time, time + self.measure_time):
            rs = self.logging_data_list_per_gen[i][t - 1]
            assert t == rs["time"]
            rs = get_reward_from_features(rs['state'])
            r = cal_reward(rs, rewards_components)
            list_r.append(r)
        r_average = np.average(list_r)

        return r_instant, r_average

    def judge_action(self, time, i):
        action = self.logging_data_list_per_gen[i][time - 1]['action']
        if action == -1:
            raise ValueError
        return action

    def make_reward(self, folder, i):
        if self.samples_all_intersection[i] is None:
            self.samples_all_intersection[i] = []
        if i % 100 == 0:
            print("make reward for inter {0} in folder {1}".format(i, folder))
        list_samples = []
        try:
            last_logged_time = int(self.logging_data_list_per_gen[i][-1]['time'])
            required_horizon = max(self.interval, self.measure_time)
            # A sample is valid only when reward and next state both exist.
            for time in range(
                1,
                last_logged_time - required_horizon + 1,
                self.interval,
            ):
                state = self.construct_state(self.dic_traffic_env_conf["LIST_STATE_FEATURE"], time, i)
                reward_instant, reward_average = self.construct_reward(self.dic_traffic_env_conf["DIC_REWARD_INFO"],
                                                                       time, i)
                action = self.judge_action(time, i)

                next_state = self.construct_state(
                    self.dic_traffic_env_conf["LIST_STATE_FEATURE"],
                    time + self.interval,
                    i,
                )
                training_reward = (
                    reward_instant
                    if self.reward_aggregation == "end"
                    else reward_average
                )
                sample = [state, action, next_state, training_reward, reward_instant, time,
                          folder+"-"+"round_{0}".format(self.cnt_round)]
                list_samples.append(sample)

            self.samples_all_intersection[i].extend(list_samples)
            return 1
        except:
            print("Error occurs when making rewards in generator {0} for intersection {1}".format(folder, i))
            print('traceback.format_exc():\n%s' % traceback.format_exc())
            return 0

    def make_reward_for_system(self):
        for folder in os.listdir(self.path_to_samples):
            print(folder)
            if "generator" not in folder:
                continue
            if not self.load_data_for_system(folder):
                continue
            for i in range(self.dic_traffic_env_conf['NUM_INTERSECTIONS']):
                pass_code = self.make_reward(folder, i)
                if pass_code == 0:
                    continue

        for i in range(self.dic_traffic_env_conf['NUM_INTERSECTIONS']):
            self.dump_sample(self.samples_all_intersection[i], "inter_{0}".format(i))

    def dump_sample(self, samples, folder):
        if folder == "":
            with open(os.path.join(self.parent_dir, "total_samples.pkl"), "ab+") as f:
                pickle.dump(samples, f, -1)
        elif "inter" in folder:
            with open(os.path.join(self.parent_dir, "total_samples_{0}.pkl".format(folder)), "ab+") as f:
                pickle.dump(samples, f, -1)
        else:
            with open(os.path.join(self.path_to_samples, folder, "samples_{0}.pkl".format(folder)), 'wb') as f:
                pickle.dump(samples, f, -1)
