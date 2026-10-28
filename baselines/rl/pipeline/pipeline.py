"""RL training pipeline orchestration.

One training round = rollout generators → replay-sample construction →
network update → test evaluation, then a final evaluation with hourly
checkpoints.  Implementation notes: ``dump_json`` is inlined, the
state-action logging is dropped, ``copy_conf_file`` writes ``agent.conf`` into
``PATH_TO_MODEL`` at the end of training (so evaluation can recover the exact
training hyperparameters next to the checkpoints), and model_test is handed
the work directory explicitly.
"""

from baselines.rl.pipeline.generator import Generator
from baselines.rl.pipeline.construct_sample import ConstructSample
from baselines.rl.pipeline.updater import Updater
from baselines.rl.pipeline import model_test
import json
import shutil
import time
from multiprocessing import Process, Queue
from queue import Empty
import numpy as np
import copy
import os
from jevlight.wandb_utils import safe_wandb_finish, safe_wandb_log, wandb_init_if_enabled


def dump_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f)


def merge(dic_tmp, dic_to_change):
    dic_result = copy.deepcopy(dic_tmp)
    dic_result.update(dic_to_change)
    return dic_result


def path_check(dic_path):
    # Idempotent: create the work/model dirs if missing (see the source's
    # note on decoupled sub-rollouts).
    os.makedirs(dic_path["PATH_TO_WORK_DIRECTORY"], exist_ok=True)
    os.makedirs(dic_path["PATH_TO_MODEL"], exist_ok=True)


def copy_conf_file(dic_path, dic_agent_conf, dic_traffic_env_conf, path=None):
    if path is None:
        path = dic_path["PATH_TO_WORK_DIRECTORY"]
    json.dump(dic_agent_conf, open(os.path.join(path, "agent.conf"), "w"), indent=4)
    json.dump(dic_traffic_env_conf, open(os.path.join(path, "traffic_env.conf"), "w"), indent=4)


def dump_agent_conf_into_model_dir(dic_path, dic_agent_conf):
    """Write agent.conf next to the checkpoints for the evaluation entry.

    PORT NOTE: only called at the END of a training run.  The agents'
    constructors treat a non-empty model directory as "resume" and force-load
    ``round_0_inter_0``, so the file must not exist while agents are being
    built on a fresh run.
    """
    json.dump(dic_agent_conf, open(os.path.join(dic_path["PATH_TO_MODEL"], "agent.conf"), "w"), indent=4)


def copy_sim_file(dic_path, dic_traffic_env_conf, path=None):
    if path is None:
        path = dic_path["PATH_TO_WORK_DIRECTORY"]
    shutil.copy(os.path.join(dic_path["PATH_TO_DATA"], dic_traffic_env_conf["TRAFFIC_FILE"]),
                os.path.join(path, dic_traffic_env_conf["TRAFFIC_FILE"]))
    shutil.copy(os.path.join(dic_path["PATH_TO_DATA"], dic_traffic_env_conf["ROADNET_FILE"]),
                os.path.join(path, dic_traffic_env_conf["ROADNET_FILE"]))


def generator_wrapper(
    cnt_round,
    cnt_gen,
    dic_path,
    dic_agent_conf,
    dic_traffic_env_conf,
    logger=None,
    result_queue=None,
):
    generator = Generator(cnt_round=cnt_round,
                          cnt_gen=cnt_gen,
                          dic_path=dic_path,
                          dic_agent_conf=dic_agent_conf,
                          dic_traffic_env_conf=dic_traffic_env_conf)
    print("make generator")
    result = generator.generate(logger)
    if result_queue is not None:
        result_queue.put((cnt_gen, result))
    print("generator_wrapper end")
    return result

def updater_wrapper(cnt_round, dic_agent_conf, dic_traffic_env_conf, dic_path):
    updater = Updater(
        cnt_round=cnt_round,
        dic_agent_conf=dic_agent_conf,
        dic_traffic_env_conf=dic_traffic_env_conf,
        dic_path=dic_path
    )
    updater.load_sample_for_agents()
    updater.update_network_for_agents()
    print("updater_wrapper end")
    return


class Pipeline:

    def __init__(self, dic_agent_conf, dic_traffic_env_conf, dic_path, roadnet, trafficflow):
        self.dic_agent_conf = dic_agent_conf
        self.dic_traffic_env_conf = dic_traffic_env_conf
        self.dic_path = dic_path
        self.roadnet = roadnet
        self.trafficflow = trafficflow

        self.initialize()

    def initialize(self):
        path_check(self.dic_path)
        copy_conf_file(self.dic_path, self.dic_agent_conf, self.dic_traffic_env_conf)
        copy_sim_file(self.dic_path, self.dic_traffic_env_conf)

    def run(self, round, multi_process=False):
        f_time = open(os.path.join(self.dic_path["PATH_TO_WORK_DIRECTORY"], "running_time.csv"), "w")
        f_time.write("generator_time\tmaking_samples_time\tupdate_network_time\ttest_evaluation_times\tall_times\n")
        f_time.close()

        # wandb init
        all_config = merge(merge(self.dic_agent_conf, self.dic_path), self.dic_traffic_env_conf)
        logger = wandb_init_if_enabled(
            self.dic_traffic_env_conf,
            project=self.dic_traffic_env_conf['PROJECT_NAME'],
            group=f"{self.dic_traffic_env_conf['MODEL']}-{self.dic_traffic_env_conf['ROADNET_FILE']}-{self.dic_traffic_env_conf['TRAFFIC_FILE']}-{len(self.dic_traffic_env_conf['PHASE'])}_Phases",
            name=f"round_{round}",
            config=all_config,
        )
        if logger is not None:
            logger.define_metric("train/round")
            logger.define_metric("final/checkpoint")
            for metric_name in (
                "train/reward",
                "train/avg_queue_len",
                "train/queuing_vehicle_num",
                "train/avg_waiting_time",
                "train/avg_travel_time",
                "train/vehicle_count",
                "train/arrived_vehicle_count",
                "train/observed_vehicle_count",
                "train/intersection_observation_count",
                "train/queue_observation_step_count",
            ):
                logger.define_metric(metric_name, step_metric="train/round")
            logger.define_metric("test/round")
            for metric_name in (
                "test/reward",
                "test/avg_travel_time",
                "test/avg_waiting_time",
                "test/avg_queue_len",
                "test/queuing_vehicle_num",
                "test/vehicle_count",
                "test/arrived_vehicle_count",
                "test/observed_vehicle_count",
                "test/intersection_observation_count",
                "test/queue_observation_step_count",
            ):
                logger.define_metric(
                    metric_name,
                    step_metric="test/round",
                )
            for metric_name in (
                "final/reward",
                "final/avg_travel_time",
                "final/avg_waiting_time",
                "final/avg_queue_len",
                "final/queuing_vehicle_num",
                "final/vehicle_count",
                "final/arrived_vehicle_count",
                "final/observed_vehicle_count",
                "final/intersection_observation_count",
                "final/queue_observation_step_count",
            ):
                logger.define_metric(
                    metric_name,
                    step_metric="final/checkpoint",
                )

        last_10_results = {"test_reward_over": [],
                           "test_avg_queue_len_over": [],
                           "test_queuing_vehicle_num_over": [],
                           "test_avg_waiting_time_over": [],
                           "test_avg_travel_time_over": []}
        for cnt_round in range(self.dic_traffic_env_conf["NUM_ROUNDS"]):
            print("round %d starts" % cnt_round)
            round_start_time = time.time()
            process_list = []

            print("==============  generator =============")
            generator_start_time = time.time()
            generator_results = []
            if multi_process:
                print("-------------- use multi-process for generator -------------")
                result_queue = Queue()
                for cnt_gen in range(self.dic_traffic_env_conf["NUM_GENERATORS"]):
                    p = Process(target=generator_wrapper,
                                args=(cnt_round, cnt_gen, self.dic_path,
                                      self.dic_agent_conf, self.dic_traffic_env_conf,
                                      None, result_queue)
                                )
                    print("before")
                    p.start()
                    print("end")
                    process_list.append(p)
                print("before join")
                for i in range(len(process_list)):
                    p = process_list[i]
                    print("generator %d to join" % i)
                    p.join()
                    print("generator %d finish join" % i)
                successful_generators = sum(
                    process.exitcode == 0 for process in process_list
                )
                for _ in range(successful_generators):
                    try:
                        _, generator_result = result_queue.get(timeout=5)
                    except Empty:
                        break
                    generator_results.append(generator_result)
                result_queue.close()
                print("end join")
            else:
                for cnt_gen in range(self.dic_traffic_env_conf["NUM_GENERATORS"]):
                    generator_results.append(
                        generator_wrapper(
                            cnt_round=cnt_round,
                            cnt_gen=cnt_gen,
                            dic_path=self.dic_path,
                            dic_agent_conf=self.dic_agent_conf,
                            dic_traffic_env_conf=self.dic_traffic_env_conf,
                        )
                    )
            generator_end_time = time.time()
            generator_total_time = generator_end_time - generator_start_time
            valid_generator_results = [
                result for result in generator_results if result
            ]
            if valid_generator_results:
                safe_wandb_log(logger, {
                    "train/round": cnt_round,
                    "train/reward": float(np.mean([
                        result.get("training_reward", 0.0)
                        for result in valid_generator_results
                    ])),
                    "train/avg_queue_len": float(np.mean([
                        result.get("avg_queue_len", 0.0)
                        for result in valid_generator_results
                    ])),
                    "train/queuing_vehicle_num": float(np.mean([
                        result.get("queuing_vehicle_num", 0.0)
                        for result in valid_generator_results
                    ])),
                    "train/avg_waiting_time": float(np.mean([
                        result.get("avg_waiting_time", 0.0)
                        for result in valid_generator_results
                    ])),
                    "train/avg_travel_time": float(np.mean([
                        result.get("avg_travel_time", 0.0)
                        for result in valid_generator_results
                    ])),
                    "train/vehicle_count": float(np.mean([
                        result.get("vehicle_count", 0.0)
                        for result in valid_generator_results
                    ])),
                    "train/arrived_vehicle_count": float(np.mean([
                        result.get("arrived_vehicle_count", 0.0)
                        for result in valid_generator_results
                    ])),
                    "train/observed_vehicle_count": float(np.mean([
                        result.get("observed_vehicle_count", 0.0)
                        for result in valid_generator_results
                    ])),
                    "train/intersection_observation_count": float(np.mean([
                        result.get("intersection_observation_count", 0.0)
                        for result in valid_generator_results
                    ])),
                    "train/queue_observation_step_count": float(np.mean([
                        result.get("queue_observation_step_count", 0.0)
                        for result in valid_generator_results
                    ])),
                })

            print("==============  make samples =============")
            # make samples and determine which samples are good
            making_samples_start_time = time.time()
            train_round = os.path.join(self.dic_path["PATH_TO_WORK_DIRECTORY"], "train_round")
            if not os.path.exists(train_round):
                os.makedirs(train_round)
            if self.dic_traffic_env_conf["MODEL_NAME"] == "CityLight":
                print(
                    "CityLight uses the original on-policy rollout files; "
                    "generic replay sample construction is skipped."
                )
            else:
                cs = ConstructSample(path_to_samples=train_round, cnt_round=cnt_round,
                                     dic_traffic_env_conf=self.dic_traffic_env_conf)
                cs.make_reward_for_system()
            making_samples_end_time = time.time()
            making_samples_total_time = making_samples_end_time - making_samples_start_time

            print("==============  update network =============")
            update_network_start_time = time.time()
            if self.dic_traffic_env_conf["MODEL_NAME"] in self.dic_traffic_env_conf["LIST_MODEL_NEED_TO_UPDATE"]:
                if multi_process:
                    p = Process(target=updater_wrapper,
                                args=(cnt_round,
                                      self.dic_agent_conf,
                                      self.dic_traffic_env_conf,
                                      self.dic_path))
                    p.start()
                    print("update to join")
                    p.join()
                    print("update finish join")
                else:
                    updater_wrapper(cnt_round=cnt_round,
                                    dic_agent_conf=self.dic_agent_conf,
                                    dic_traffic_env_conf=self.dic_traffic_env_conf,
                                    dic_path=self.dic_path)

            update_network_end_time = time.time()
            update_network_total_time = update_network_end_time - update_network_start_time

            print("==============  test evaluation =============")
            test_evaluation_start_time = time.time()
            test_run_counts = int(
                self.dic_traffic_env_conf.get(
                    "DEVELOPMENT_DURATION",
                    self.dic_traffic_env_conf["RUN_COUNTS"],
                )
                or self.dic_traffic_env_conf["RUN_COUNTS"]
            )
            results = model_test.test(
                self.dic_path["PATH_TO_MODEL"],
                self.dic_path["PATH_TO_DATA"],
                cnt_round,
                test_run_counts,
                self.dic_traffic_env_conf,
                logger,
                start_time=0,
                evaluation_name="test",
                work_dir=self.dic_path["PATH_TO_WORK_DIRECTORY"],
            )
            safe_wandb_log(logger, {
                "test/round": cnt_round,
                "test/reward": results["test_reward_over"],
                "test/avg_queue_len": results["test_avg_queue_len_over"],
                "test/queuing_vehicle_num": results["test_queuing_vehicle_num_over"],
                "test/avg_waiting_time": results["test_avg_waiting_time_over"],
                "test/avg_travel_time": results["test_avg_travel_time_over"],
                "test/vehicle_count": results["test_vehicle_count"],
                "test/arrived_vehicle_count": results["test_arrived_vehicle_count"],
                "test/observed_vehicle_count": results["test_observed_vehicle_count"],
                "test/intersection_observation_count": results[
                    "test_intersection_observation_count"
                ],
                "test/queue_observation_step_count": results[
                    "test_queue_observation_step_count"
                ],
            })
            if cnt_round + 1 > self.dic_traffic_env_conf["NUM_ROUNDS"] - 10:
                for ele in last_10_results:
                    last_10_results[ele].append(results[ele])

            test_evaluation_end_time = time.time()
            test_evaluation_total_time = test_evaluation_end_time - test_evaluation_start_time

            print("Generator time: ", generator_total_time)
            print("Making samples time:", making_samples_total_time)
            print("update_network time:", update_network_total_time)
            print("test_evaluation time:", test_evaluation_total_time)

            print("round {0} ends, total_time: {1}".format(cnt_round, time.time() - round_start_time))
            f_time = open(os.path.join(self.dic_path["PATH_TO_WORK_DIRECTORY"], "running_time.csv"), "a")
            f_time.write("{0}\t{1}\t{2}\t{3}\t{4}\n".format(generator_total_time, making_samples_total_time,
                                                            update_network_total_time, test_evaluation_total_time,
                                                            time.time() - round_start_time))
            f_time.close()

        last_10_results = {ele: np.mean(last_10_results[ele]) for ele in last_10_results}
        print(last_10_results)

        final_start_time = int(
            self.dic_traffic_env_conf["FINAL_START_TIME"]
        )
        final_duration = int(
            self.dic_traffic_env_conf["FINAL_DURATION"]
        )
        model_test.test(
            self.dic_path["PATH_TO_MODEL"],
            self.dic_path["PATH_TO_DATA"],
            self.dic_traffic_env_conf["NUM_ROUNDS"] - 1,
            final_duration,
            self.dic_traffic_env_conf,
            logger,
            start_time=final_start_time,
            evaluation_name="final",
            checkpoint_interval=int(
                self.dic_traffic_env_conf["CHECKPOINT_INTERVAL"]
            ),
            work_dir=self.dic_path["PATH_TO_WORK_DIRECTORY"],
        )
        safe_wandb_finish(logger)
        dump_agent_conf_into_model_dir(self.dic_path, self.dic_agent_conf)

        return results
