import numpy as np
import tensorflow as tf
from tensorflow.keras.layers import Layer, Reshape
from tensorflow.keras.models import model_from_json, load_model
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras import backend as K
import random
import os
from .agent import Agent
import traceback

# Keras 3 safe-mode rejects Lambda layers whose function is a Python lambda.
# Everything deserialized here (to_json round-trips and our own checkpoints)
# originates from this code, so lift the restriction. Keras 2 has no such mode.
try:
    tf.keras.config.enable_unsafe_deserialization()
except AttributeError:
    pass


class NetworkAgent(Agent):
    def __init__(self, dic_agent_conf, dic_traffic_env_conf, dic_path, cnt_round, intersection_id="0"):
        super(NetworkAgent, self).__init__(
            dic_agent_conf, dic_traffic_env_conf, dic_path, intersection_id=intersection_id)

        # ===== check num actions == num phases ============
        self.num_actions = len(dic_traffic_env_conf["PHASE"])
        self.num_phases = len(dic_traffic_env_conf["PHASE"])
        # self.num_lanes = np.sum(np.array(list(self.dic_traffic_env_conf["LANE_NUM"].values())))

        self.memory = self.build_memory()
        self.cnt_round = cnt_round

        self.Xs, self.Y = None, None
        self.num_lane = dic_traffic_env_conf["NUM_LANE"]
        self.phase_map = dic_traffic_env_conf["PHASE_MAP"]

        if cnt_round == 0:

            if os.listdir(self.dic_path["PATH_TO_MODEL"]):
                self.load_network("round_0_inter_{0}".format(intersection_id))
            else:
                self.q_network = self.build_network()
            self.q_network_bar = self.build_network_from_copy(self.q_network)
        else:
            try:
                self.load_network("round_{0}_inter_{1}".format(cnt_round-1, self.intersection_id))

                if "UPDATE_Q_BAR_EVERY_C_ROUND" in self.dic_agent_conf:
                    if self.dic_agent_conf["UPDATE_Q_BAR_EVERY_C_ROUND"]:
                        self.load_network_bar("round_{0}_inter_{1}".format(
                                max((cnt_round - 1) // self.dic_agent_conf["UPDATE_Q_BAR_FREQ"] *
                                    self.dic_agent_conf["UPDATE_Q_BAR_FREQ"], 0), self.intersection_id))
                    else:
                        self.load_network_bar("round_{0}_inter_{1}".format(
                            max(cnt_round - self.dic_agent_conf["UPDATE_Q_BAR_FREQ"], 0),
                            self.intersection_id))
                else:
                    self.load_network_bar("round_{0}_inter_{1}".format(
                            max(cnt_round - self.dic_agent_conf["UPDATE_Q_BAR_FREQ"], 0), self.intersection_id))
            except Exception:
                print('traceback.format_exc():\n%s' % traceback.format_exc())

        # decay the epsilon
        decayed_epsilon = self.dic_agent_conf["EPSILON"] * pow(self.dic_agent_conf["EPSILON_DECAY"], cnt_round)
        self.dic_agent_conf["EPSILON"] = max(decayed_epsilon, self.dic_agent_conf["MIN_EPSILON"])

    def load_network(self, file_name, file_path=None):
        if file_path is None:
            file_path = self.dic_path["PATH_TO_MODEL"]
        self.q_network = self._load_keras_network(
            os.path.join(file_path, "%s.h5" % file_name)
        )
        print("succeed in loading model %s" % file_name)

    def load_network_transfer(self, file_name, file_path=None):
        if file_path is None:
            file_path = self.dic_path["PATH_TO_TRANSFER_MODEL"]
        self.q_network = self._load_keras_network(
            os.path.join(file_path, "%s.h5" % file_name)
        )
        print("succeed in loading model %s" % file_name)

    def load_network_bar(self, file_name, file_path=None):
        if file_path is None:
            file_path = self.dic_path["PATH_TO_MODEL"]
        self.q_network_bar = self._load_keras_network(
            os.path.join(file_path, "%s.h5" % file_name)
        )
        print("succeed in loading model %s" % file_name)

    def save_network(self, file_name):
        self.q_network.save(os.path.join(self.dic_path["PATH_TO_MODEL"], "%s.h5" % file_name))

    def save_network_bar(self, file_name):
        self.q_network_bar.save(os.path.join(self.dic_path["PATH_TO_MODEL"], "%s.h5" % file_name))

    def build_network(self):
        raise NotImplementedError

    @staticmethod
    def build_memory():
        return []

    def build_network_from_copy(self, network_copy):
        """Initialize a Q network from a copy"""
        network_structure = network_copy.to_json()
        network_weights = network_copy.get_weights()
        network = model_from_json(
            network_structure,
            custom_objects=_network_custom_objects(),
        )
        network.set_weights(network_weights)
        network.compile(optimizer=Adam(learning_rate=self.dic_agent_conf["LEARNING_RATE"]),
                        loss=self.dic_agent_conf["LOSS_FUNCTION"])
        return network

    def _load_keras_network(self, path):
        """Load legacy graph-model checkpoints with all MPLight Lambda helpers.

        MPLight serializes ``slice_tensor`` and ``relation`` in Lambda layers.
        Keras 3 no longer looks these module functions up implicitly, so every
        load/copy route must provide the custom-object registry explicitly.
        """
        network = load_model(
            path,
            custom_objects=_network_custom_objects(),
            compile=False,
        )
        network.compile(
            optimizer=Adam(learning_rate=self.dic_agent_conf["LEARNING_RATE"]),
            loss=self.dic_agent_conf["LOSS_FUNCTION"],
        )
        return network

    def prepare_Xs_Y(self, memory):

        ind_end = len(memory)
        print("memory size before forget: {0}".format(ind_end))
        # use all the samples to pretrain, i.e., without forgetting
        ind_sta = max(0, ind_end - self.dic_agent_conf["MAX_MEMORY_LEN"])
        memory_after_forget = memory[ind_sta: ind_end]
        print("memory size after forget:", len(memory_after_forget))

        # sample the memory
        sample_size = min(self.dic_agent_conf["SAMPLE_SIZE"], len(memory_after_forget))
        sample_slice = random.sample(memory_after_forget, sample_size)
        print("memory samples number:", sample_size)

        dic_state_feature_arrays = {}
        for feature_name in self.dic_traffic_env_conf["LIST_STATE_FEATURE"]:
            dic_state_feature_arrays[feature_name] = []
        Y = []

        for i in range(len(sample_slice)):
            sample = sample_slice[i]
            if isinstance(sample, dict) and sample.get("async"):
                state = sample["state"]
                action = sample["action"]
                next_state = sample["next_state"]
                reward = sample["reward"]
            else:
                state, action, next_state, reward, instant_reward, _, _ = sample
            for feature_name in self.dic_traffic_env_conf["LIST_STATE_FEATURE"]:
                dic_state_feature_arrays[feature_name].append(
                    self._encode_state_feature(state, feature_name)
                )
            _state = []
            _next_state = []
            for feature_name in self.dic_traffic_env_conf["LIST_STATE_FEATURE"]:
                _state.append(np.array([
                    self._encode_state_feature(state, feature_name)
                ]))
                _next_state.append(np.array([
                    self._encode_state_feature(next_state, feature_name)
                ]))

            target = self.q_network.predict(_state)

            next_state_qvalues = self.q_network_bar.predict(_next_state)

            if self.dic_agent_conf["LOSS_FUNCTION"] == "mean_squared_error":
                final_target = np.copy(target[0])
                decision_interval = float(
                    self.dic_traffic_env_conf.get("MIN_ACTION_TIME", 15) or 15
                )
                duration = (
                    float(
                        sample.get("duration", decision_interval)
                        or decision_interval
                    )
                    if isinstance(sample, dict)
                    else decision_interval
                )
                gamma = self.dic_agent_conf["GAMMA"] ** (
                    duration / decision_interval
                )
                final_target[action] = reward / self.dic_agent_conf["NORMAL_FACTOR"] + gamma * \
                                       np.max(next_state_qvalues[0])
            elif self.dic_agent_conf["LOSS_FUNCTION"] == "categorical_crossentropy":
                raise NotImplementedError

            Y.append(final_target)

        self.Xs = [np.array(dic_state_feature_arrays[feature_name]) for feature_name in
                   self.dic_traffic_env_conf["LIST_STATE_FEATURE"]]
        self.Y = np.array(Y)

    def _encode_state_feature(self, state, feature_name):
        value = state[feature_name]
        if (
            "cur_phase" in feature_name
            and self.dic_traffic_env_conf.get("BINARY_PHASE_EXPANSION", False)
        ):
            if isinstance(value, (list, tuple, np.ndarray)) and len(value) == 8:
                return list(value)
            phase_idx = int(value[0] if isinstance(value, (list, tuple, np.ndarray)) else value)
            return self.dic_traffic_env_conf["PHASE"][phase_idx]
        return list(value) if isinstance(value, (list, tuple, np.ndarray)) else [value]

    def convert_state_to_input(self, s):
        if self.dic_traffic_env_conf["BINARY_PHASE_EXPANSION"]:
            inputs = []
            for feature in self.dic_traffic_env_conf["LIST_STATE_FEATURE"]:
                if "cur_phase" in feature:
                    inputs.append(np.array([self.dic_traffic_env_conf['PHASE'][s[feature][0]]]))
                else:
                    inputs.append(np.array([s[feature]]))
            return inputs
        else:
            return [np.array([s[feature]]) for feature in self.dic_traffic_env_conf["LIST_STATE_FEATURE"]]

    def choose_action(self, count, state):
        """choose the best action for current state """
        state_input = self.convert_state_to_input(state)
        q_values = self.q_network.predict(state_input)
        if random.random() <= self.dic_agent_conf["EPSILON"]:  # continue explore new Random Action
            action = random.randrange(len(q_values[0]))
        else:  # exploitation
            action = np.argmax(q_values[0])
        return action

    def train_network(self):
        epochs = self.dic_agent_conf["EPOCHS"]
        sample_count = len(self.Y)
        batch_size = min(self.dic_agent_conf["BATCH_SIZE"], sample_count)
        validate_this_round = self.dic_agent_conf.get("RL_VALIDATE_THIS_ROUND", True)
        validation_split = 0.3 if validate_this_round and sample_count >= 2 else 0.0
        callbacks = []
        if validation_split:
            callbacks.append(EarlyStopping(
                monitor='val_loss', patience=self.dic_agent_conf["PATIENCE"], verbose=0, mode='min'))
        else:
            reason = "one sample available" if sample_count < 2 else "scheduled interval"
            print(f"NetworkAgent: training without validation ({reason})")

        self.q_network.fit(self.Xs, self.Y, batch_size=batch_size, epochs=epochs, shuffle=False,
                           verbose=2, validation_split=validation_split, callbacks=callbacks)


class Selector(Layer):

    def __init__(self, select, d_phase_encoding, d_action, **kwargs):
        super(Selector, self).__init__(**kwargs)
        self.select = select
        self.d_phase_encoding = d_phase_encoding
        self.d_action = d_action
        self.select_neuron = K.constant(value=self.select, shape=(1, self.d_phase_encoding))

    def build(self, input_shape):
        # Create a trainable weight variable for this layer.
        super(Selector, self).build(input_shape)

    def call(self, x):
        batch_size = K.shape(x)[0]
        constant = K.tile(self.select_neuron, (batch_size, 1))
        return K.min(K.cast(K.equal(x, constant), dtype="float32"), axis=-1, keepdims=True)

    def get_config(self):
        config = {"select": self.select, "d_phase_encoding": self.d_phase_encoding, "d_action": self.d_action}
        base_config = super(Selector, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

    def compute_output_shape(self, input_shape):
        batch_size = input_shape[0]
        return [batch_size, self.d_action]


def slice_tensor(x, index):
    x_shape = K.int_shape(x)
    if len(x_shape) == 3:
        return x[:, index, :]
    elif len(x_shape) == 2:
        return Reshape((1, ))(x[:, index])


def relation(x, phase_list):
    relations = []
    num_phase = len(phase_list)
    if num_phase == 8:
        for p1 in phase_list:
            zeros = [0, 0, 0, 0, 0, 0, 0]
            count = 0
            for p2 in phase_list:
                if p1 == p2:
                    continue
                m1 = p1.split("_")
                m2 = p2.split("_")
                if len(list(set(m1 + m2))) == 3:
                    zeros[count] = 1
                count += 1
            relations.append(zeros)
        relations = np.array(relations).reshape((1, 8, 7))
    else:
        relations = np.array([[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]]).reshape((1, 4, 3))
    batch_size = K.shape(x)[0]
    constant = K.constant(relations)
    constant = K.tile(constant, (batch_size, 1, 1))
    return constant


def sum_competing_phase_q(x):
    """Reduce MPLight's per-action competing-phase scores to Q values."""
    return K.sum(x, axis=2)


def _network_custom_objects():
    """Return all custom layers/functions used by NetworkAgent subclasses."""
    return {
        "Selector": Selector,
        "slice_tensor": slice_tensor,
        "relation": relation,
        "sum_competing_phase_q": sum_competing_phase_q,
    }


class RepeatVector3D(Layer):
    def __init__(self, times, **kwargs):
        super(RepeatVector3D, self).__init__(**kwargs)
        self.times = times

    def compute_output_shape(self, input_shape):
        return input_shape[0], self.times, input_shape[1], input_shape[2]

    def call(self, inputs):
        # [batch,agent,dim]->[batch,1,agent,dim]
        # [batch,1,agent,dim]->[batch,agent,agent,dim]
        return K.tile(K.expand_dims(inputs, 1), [1, self.times, 1, 1])

    def get_config(self):
        config = {'times': self.times}
        base_config = super(RepeatVector3D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))
