"""
Colgiht agent.
observations: [lane_num_vehicle, cur_phase]
reward: -queue_length
"""
import numpy as np
import os
from .agent import Agent
import random
from tensorflow.keras import backend as K
from tensorflow.keras.optimizers import Adam
import tensorflow as tf
from tensorflow.keras import Input, Model
from tensorflow.keras.layers import Dense, Lambda, Layer, Reshape
from tensorflow.keras.models import model_from_json, load_model
from tensorflow.keras.utils import to_categorical
from tensorflow.keras.callbacks import EarlyStopping
# The ``import torch`` lives inside choose_action_with_value — the only
# consumer — so a TensorFlow-only install can run CoLight without torch.

# Keras 3 safe-mode rejects Lambda layers whose function is a Python lambda.
# Everything deserialized here (to_json round-trips and our own checkpoints)
# originates from this code, so lift the restriction. Keras 2 has no such mode.
try:
    tf.keras.config.enable_unsafe_deserialization()
except AttributeError:
    pass


def build_memory():
    return []


# State entries carried alongside the observation but never concatenated into
# the Q-network input: the neighbour adjacency and the per-intersection
# canonical-phase availability mask.
_NON_INPUT_FEATURES = ("adjacency_matrix", "available_actions")


class CoLightAgent(Agent):
    def __init__(self, dic_agent_conf=None, dic_traffic_env_conf=None, dic_path=None, cnt_round=None,
                 intersection_id="0"):
        super(CoLightAgent, self).__init__(
            dic_agent_conf, dic_traffic_env_conf, dic_path, intersection_id)
        self.CNN_layers = dic_agent_conf['CNN_layers']
        self.num_agents = dic_traffic_env_conf['NUM_INTERSECTIONS']
        self.num_neighbors = min(dic_traffic_env_conf['TOP_K_ADJACENCY'], self.num_agents)

        self.num_actions = len(self.dic_traffic_env_conf["PHASE"])
        self.len_feature = self._cal_len_feature()
        self.memory = build_memory()

        if cnt_round == 0:
            # initialization
            self.q_network = self.build_network()
            if os.listdir(self.dic_path["PATH_TO_MODEL"]):
                self.q_network.load_weights(
                    os.path.join(self.dic_path["PATH_TO_MODEL"], "round_0_inter_{0}.h5".format(intersection_id)),
                    by_name=True)
            self.q_network_bar = self.build_network_from_copy(self.q_network)
        else:
            try:
                self.load_network("round_{0}_inter_{1}".format(cnt_round - 1, self.intersection_id))
                if "UPDATE_Q_BAR_EVERY_C_ROUND" in self.dic_agent_conf:
                    if self.dic_agent_conf["UPDATE_Q_BAR_EVERY_C_ROUND"]:
                        self.load_network_bar("round_{0}_inter_{1}".format(
                            max((cnt_round - 1) // self.dic_agent_conf["UPDATE_Q_BAR_FREQ"] * self.dic_agent_conf[
                                "UPDATE_Q_BAR_FREQ"], 0),
                            self.intersection_id))
                    else:
                        self.load_network_bar("round_{0}_inter_{1}".format(
                            max(cnt_round - self.dic_agent_conf["UPDATE_Q_BAR_FREQ"], 0),
                            self.intersection_id))
                else:
                    self.load_network_bar("round_{0}_inter_{1}".format(
                        max(cnt_round - self.dic_agent_conf["UPDATE_Q_BAR_FREQ"], 0), self.intersection_id))
            except:
                print("fail to load network, current round: {0}".format(cnt_round))

        if self.dic_agent_conf.get("EPSILON_IS_CURRENT", False):
            decayed_epsilon = self.dic_agent_conf["EPSILON"]
        else:
            decayed_epsilon = self.dic_agent_conf["EPSILON"] * pow(
                self.dic_agent_conf["EPSILON_DECAY"], cnt_round
            )
        self.dic_agent_conf["EPSILON"] = max(
            decayed_epsilon, self.dic_agent_conf["MIN_EPSILON"]
        )

    def _decay_sampling_epsilon(self):
        """Apply the optional per-action exploration schedule."""
        epsilon_gamma = float(
            self.dic_agent_conf.get("EPSILON_STEP_GAMMA", 1.0)
        )
        if epsilon_gamma < 1.0:
            self.dic_agent_conf["EPSILON"] = max(
                float(self.dic_agent_conf["MIN_EPSILON"]),
                float(self.dic_agent_conf["EPSILON"]) * epsilon_gamma,
            )

    def _used_state_features(self):
        """Observation features fed into the Q-network input."""
        return [
            feature
            for feature in self.dic_traffic_env_conf["LIST_STATE_FEATURE"]
            if feature not in _NON_INPUT_FEATURES
        ]

    @staticmethod
    def _normalize_action_mask(mask, num_actions):
        """Sanitize one intersection's availability mask, defaulting to all-on."""
        if mask is None:
            return np.ones(num_actions, dtype=np.float32)
        mask = np.asarray(mask, dtype=np.float32).reshape(-1)
        if mask.size != num_actions or not np.any(mask > 0):
            return np.ones(num_actions, dtype=np.float32)
        return (mask > 0).astype(np.float32)

    def _action_masks(self, states):
        """[num_agents, num_actions] availability; unavailable phases stay 0."""
        masks = np.ones((len(states), self.num_actions), dtype=np.float32)
        for index, state in enumerate(states):
            if isinstance(state, dict):
                masks[index] = self._normalize_action_mask(
                    state.get("available_actions"), self.num_actions
                )
        return masks

    @staticmethod
    def _apply_action_mask(q_values, masks):
        """Block unavailable actions with a large finite negative offset."""
        return q_values + (1.0 - masks) * -1e10

    def _cal_len_feature(self):
        N = 0
        used_feature = self._used_state_features()
        for feat_name in used_feature:
            if "cur_phase" in feat_name:
                N += 8
            else:
                N += 12
        return N

    @staticmethod
    def MLP(ins, layers=None):
        """
        Currently, the MLP layer 
        -input: [batch,#agents,dim]
        -outpout: [batch,#agents,dim]
        """
        if layers is None:
            layers = [128, 128]
        for layer_index, layer_size in enumerate(layers):
            if layer_index == 0:
                h = Dense(layer_size, activation='relu', kernel_initializer='random_normal',
                          name='Dense_embed_%d' % layer_index)(ins)
            else:
                h = Dense(layer_size, activation='relu', kernel_initializer='random_normal',
                          name='Dense_embed_%d' % layer_index)(h)

        return h

    def MultiHeadsAttModel(self, in_feats, in_nei, d_in=128, h_dim=16, dout=128, head=8, suffix=-1):
        """
        input: [batch, agent, dim] feature
               [batch, agent, nei, agent] adjacency
        input:[bacth,agent,128]
        output:
              [batch, agent, dim]
        """
        # [batch,agent,dim]->[batch,agent,1,dim]
        agent_repr = Reshape((self.num_agents, 1, d_in))(in_feats)

        # [batch,agent,dim]->(reshape)[batch,1,agent,dim]->(tile)[batch,agent,agent,dim]
        neighbor_repr = RepeatVector3D(self.num_agents)(in_feats)

        # [batch,agent,neighbor,agent]x[batch,agent,agent,dim]->[batch,agent,neighbor,dim]
        neighbor_repr = Lambda(
            _adjacency_matmul,
            output_shape=(self.num_agents, self.num_neighbors, d_in),
        )([in_nei, neighbor_repr])

        # attention computation
        # [batch, agent, 1, dim]->[batch, agent, 1, h_dim*head]
        agent_repr_head = Dense(h_dim * head, activation='relu', kernel_initializer='random_normal',
                                name='agent_repr_%d' % suffix)(agent_repr)
        # [batch,agent,1,h_dim,head]->[batch,agent,head,1,h_dim]
        agent_repr_head = Reshape((self.num_agents, 1, h_dim, head))(agent_repr_head)
        agent_repr_head = Lambda(
            _permute_heads_front,
            output_shape=(self.num_agents, head, 1, h_dim),
        )(agent_repr_head)

        # [batch,agent,neighbor,dim]->[batch,agent,neighbor,h_dim_head]
        neighbor_repr_head = Dense(h_dim * head, activation='relu', kernel_initializer='random_normal',
                                   name='neighbor_repr_%d' % suffix)(neighbor_repr)
        # [batch,agent,neighbor,dv,nv]->[batch,agent,nv,neighbor,dv]
        neighbor_repr_head = Reshape((self.num_agents, self.num_neighbors, h_dim, head))(neighbor_repr_head)
        neighbor_repr_head = Lambda(
            _permute_heads_front,
            output_shape=(self.num_agents, head, self.num_neighbors, h_dim),
        )(neighbor_repr_head)

        # [batch,agent,head,1,h_dim]x[batch,agent,head,neighbor,h_dim]->[batch,agent,head,1,neighbor]
        att = Lambda(
            _softmax_attention,
            output_shape=(self.num_agents, head, 1, self.num_neighbors),
        )([agent_repr_head, neighbor_repr_head])
        # [batch,agent,nv,1,neighbor]->[batch,agent,head,neighbor]
        att_record = Reshape((self.num_agents, head, self.num_neighbors))(att)

        # self embedding again
        neighbor_hidden_repr_head = Dense(h_dim * head, activation='relu', kernel_initializer='random_normal',
                                          name='neighbor_hidden_repr_%d' % suffix)(neighbor_repr)
        neighbor_hidden_repr_head = Reshape((self.num_agents, self.num_neighbors, h_dim, head))(
            neighbor_hidden_repr_head)
        neighbor_hidden_repr_head = Lambda(
            _permute_heads_front,
            output_shape=(self.num_agents, head, self.num_neighbors, h_dim),
        )(
            neighbor_hidden_repr_head)
        out = Lambda(
            _attention_matmul_mean,
            output_shape=(self.num_agents, 1, h_dim),
        )([att, neighbor_hidden_repr_head])
        out = Reshape((self.num_agents, h_dim))(out)
        out = Dense(dout, activation="relu", kernel_initializer='random_normal', name='MLP_after_relation_%d' % suffix)(
            out)
        return out, att_record

    def adjacency_index2matrix(self, adjacency_index):
        # [batch,agents,neighbors]
        adjacency_index_new = np.sort(adjacency_index, axis=-1)
        lab = to_categorical(adjacency_index_new, num_classes=self.num_agents)
        return lab

    def convert_state_to_input(self, s):
        """
        s: [state1, state2, ..., staten]
        """
        # TODO
        used_feature = self._used_state_features()
        feats0 = []
        adj = []
        for i in range(self.num_agents):
            adj.append(s[i]["adjacency_matrix"])
            tmp = []
            for feature in used_feature:
                tmp.extend(self._encode_feature(s[i], feature))

            feats0.append(tmp)
        # [1, agent, dim]
        # feats = np.concatenate([np.array([feat1]), np.array([feat2])], axis=-1)
        feats = np.array([feats0])
        # [1, agent, nei, agent]
        adj = self.adjacency_index2matrix(np.array([adj]))
        return [feats, adj]

    def _encode_feature(self, state, feature):
        value = state[feature]
        if "cur_phase" in feature and self.dic_traffic_env_conf["BINARY_PHASE_EXPANSION"]:
            if isinstance(value, (list, tuple, np.ndarray)) and len(value) == 8:
                return list(value)
            phase_idx = int(value[0] if isinstance(value, (list, tuple, np.ndarray)) else value)
            return self.dic_traffic_env_conf['PHASE'][phase_idx]
        return list(value) if isinstance(value, (list, tuple, np.ndarray)) else [value]

    def choose_action(self, count, states):
        """
        choose the best action for current state
        -input: state:[[state inter1],[state inter1]]
        -output: act: [#agents,num_actions]
        """
        xs = self.convert_state_to_input(states)
        masks = self._action_masks(states)
        q_values = np.asarray(self.q_network(xs)[0])
        if random.random() <= self.dic_agent_conf["EPSILON"]:
            # Explore only among this intersection's available phases.
            action = np.array([
                np.random.choice(np.flatnonzero(masks[i] > 0))
                for i in range(len(masks))
            ])
        else:
            action = np.argmax(self._apply_action_mask(q_values, masks), axis=1)
        self._decay_sampling_epsilon()

        return action

    def choose_action_with_value(self, count, states):
        """
        choose the best action for current state
        -input: state:[[state inter1],[state inter1]]
        -output: act: [#agents,num_actions]
        """
        xs = self.convert_state_to_input(states)
        masks = self._action_masks(states)
        q_values = np.asarray(self.q_network(xs)[0])
        if random.random() <= self.dic_agent_conf["EPSILON"]:
            action = np.array([
                np.random.choice(np.flatnonzero(masks[i] > 0))
                for i in range(len(masks))
            ])
        else:
            action = np.argmax(self._apply_action_mask(q_values, masks), axis=1)
        self._decay_sampling_epsilon()

        import torch

        norm_values = torch.softmax(
            torch.tensor(self._apply_action_mask(q_values, masks)) / 0.05, dim=1
        )
        norm_values = (norm_values - torch.min(norm_values, dim=1)[0].unsqueeze(1)) / (torch.max(norm_values, dim=1)[0].unsqueeze(1) - torch.min(norm_values, dim=1)[0].unsqueeze(1))
        norm_values = norm_values.numpy()

        return action, norm_values

    @staticmethod
    def _concat_list(ls):
        tmp = []
        for i in range(len(ls)):
            tmp += ls[i]
        return [tmp]

    def prepare_Xs_Y(self, memory):
        """
        memory: [slice_data, slice_data, ..., slice_data]
        prepare memory for training
        """
        if memory and any(samples and isinstance(samples[0], dict) for samples in memory):
            return self._prepare_async_Xs_Y(memory)

        slice_size = len(memory[0])
        _adjs = []
        # state : [feat1, feat2]
        # feati : [agent1, agent2, ..., agentn]
        _state = [[] for _ in range(self.num_agents)]
        _next_state = [[] for _ in range(self.num_agents)]
        _action = [[] for _ in range(self.num_agents)]
        _reward = [[] for _ in range(self.num_agents)]
        next_masks = np.ones(
            (slice_size, self.num_agents, self.num_actions), dtype=np.float32
        )

        used_feature = self._used_state_features()

        for i in range(slice_size):
            _adj = []
            for j in range(self.num_agents):
                state, action, next_state, reward, _, _, _ = memory[j][i]
                _action[j].append(action)
                _reward[j].append(reward)
                _adj.append(state["adjacency_matrix"])
                # TODO
                _state[j].append(self._concat_list([state[used_feature[i]] for i in range(len(used_feature))]))
                _next_state[j].append(self._concat_list([next_state[used_feature[i]] for i in range(len(used_feature))]))
                next_masks[i, j] = self._normalize_action_mask(
                    next_state.get("available_actions")
                    if isinstance(next_state, dict)
                    else None,
                    self.num_actions,
                )
            _adjs.append(_adj)
        # [batch, agent, nei, agent]
        _adjs2 = self.adjacency_index2matrix(np.array(_adjs))

        # [batch, 1, dim] -> [batch, agent, dim]
        _state2 = np.concatenate([np.array(ss) for ss in _state], axis=1)
        _next_state2 = np.concatenate([np.array(ss) for ss in _next_state], axis=1)
        target = self.q_network([_state2, _adjs2])
        next_state_qvalues = self.q_network_bar([_next_state2, _adjs2])
        masked_next_qvalues = self._apply_action_mask(next_state_qvalues, next_masks)
        # [batch, agent, num_actions]
        final_target = np.copy(target)
        for i in range(slice_size):
            for j in range(self.num_agents):
                final_target[i, j, _action[j][i]] = _reward[j][i] / self.dic_agent_conf["NORMAL_FACTOR"] + \
                                                    self.dic_agent_conf["GAMMA"] * np.max(masked_next_qvalues[i, j])

        self.Xs = [_state2, _adjs2]
        self.Y = final_target

    def _prepare_async_Xs_Y(self, memory):
        memory_after_forget = []
        for samples in memory:
            memory_after_forget.extend([
                sample for sample in samples
                if isinstance(sample, dict) and sample.get("async")
            ])

        ind_end = len(memory_after_forget)
        print("async memory size before forget: {0}".format(ind_end))
        ind_sta = max(0, ind_end - self.dic_agent_conf["MAX_MEMORY_LEN"])
        memory_after_forget = memory_after_forget[ind_sta: ind_end]
        sample_size = min(self.dic_agent_conf["SAMPLE_SIZE"], len(memory_after_forget))
        sample_slice = random.sample(memory_after_forget, sample_size) if sample_size else []
        print("async memory samples number:", sample_size)

        used_feature = self._used_state_features()
        _adjs = []
        _state = []
        _next_state = []

        for sample in sample_slice:
            state = sample.get("full_state", sample["state"])
            next_state = sample.get("full_next_state", sample["next_state"])
            _adj = []
            state_rows = []
            next_state_rows = []
            for j in range(self.num_agents):
                _adj.append(state[j]["adjacency_matrix"])
                state_rows.append(self._concat_list([
                    self._encode_feature(state[j], feature)
                    for feature in used_feature
                ])[0])
                next_state_rows.append(self._concat_list([
                    self._encode_feature(next_state[j], feature)
                    for feature in used_feature
                ])[0])
            _adjs.append(_adj)
            _state.append(state_rows)
            _next_state.append(next_state_rows)

        if not sample_slice:
            self.Xs = [np.array([]), np.array([])]
            self.Y = np.array([])
            return

        _state2 = np.array(_state)
        _next_state2 = np.array(_next_state)
        _adjs2 = self.adjacency_index2matrix(np.array(_adjs))

        target = self.q_network([_state2, _adjs2])
        next_state_qvalues = self.q_network_bar([_next_state2, _adjs2])
        final_target = np.copy(target)
        decision_interval = float(
            self.dic_traffic_env_conf.get("MIN_ACTION_TIME", 15) or 15
        )

        for i, sample in enumerate(sample_slice):
            target_intersection = int(sample.get("target_intersection", 0))
            action = int(sample["action"]) % self.num_actions
            duration = float(
                sample.get("duration", decision_interval)
                or decision_interval
            )
            gamma = self.dic_agent_conf["GAMMA"] ** (
                duration / decision_interval
            )
            sample_next_state = sample.get(
                "full_next_state", sample["next_state"]
            )
            next_state_row = (
                sample_next_state[target_intersection]
                if isinstance(sample_next_state, (list, tuple))
                and 0 <= target_intersection < len(sample_next_state)
                else None
            )
            next_state_mask = self._normalize_action_mask(
                next_state_row.get("available_actions")
                if isinstance(next_state_row, dict)
                else None,
                self.num_actions,
            )
            masked_next_qvalues = self._apply_action_mask(
                next_state_qvalues[i, target_intersection], next_state_mask
            )
            final_target[i, target_intersection, action] = (
                sample["reward"] / self.dic_agent_conf["NORMAL_FACTOR"]
                + gamma * np.max(masked_next_qvalues)
            )

        self.Xs = [_state2, _adjs2]
        self.Y = final_target

    def build_network(self, MLP_layers=[32, 32]):
        CNN_layers = self.CNN_layers
        CNN_heads = [5] * len(CNN_layers)
        In = list()
        # In: [batch,agent,dim]
        # In: [batch,agent,neighbors,agents]
        In.append(Input(shape=(self.num_agents, self.len_feature), name="feature"))
        In.append(Input(shape=(self.num_agents, self.num_neighbors, self.num_agents), name="adjacency_matrix"))

        feature = self.MLP(In[0], MLP_layers)

        # feature:[batch,agents,feature_dim]
        print("CNN_heads:", CNN_heads)
        for CNN_layer_index, CNN_layer_size in enumerate(CNN_layers):
            print("CNN_heads[CNN_layer_index]:", CNN_heads[CNN_layer_index])
            if CNN_layer_index == 0:
                h, _ = self.MultiHeadsAttModel(
                    feature,
                    In[1],
                    d_in=MLP_layers[-1],
                    h_dim=CNN_layer_size[0],
                    dout=CNN_layer_size[1],
                    head=CNN_heads[CNN_layer_index],
                    suffix=CNN_layer_index
                )
            else:
                h, _ = self.MultiHeadsAttModel(
                    h,
                    In[1],
                    d_in=MLP_layers[-1],
                    h_dim=CNN_layer_size[0],
                    dout=CNN_layer_size[1],
                    head=CNN_heads[CNN_layer_index],
                    suffix=CNN_layer_index
                )
        # action prediction layer
        # [batch,agent,32]->[batch,agent,action]
        out = Dense(self.num_actions, kernel_initializer='random_normal', name='action_layer')(h)
        # out:[batch,agent,action], att:[batch,layers,agent,head,neighbors]
        model = Model(inputs=In, outputs=out)

        model.compile(optimizer=Adam(learning_rate=self.dic_agent_conf["LEARNING_RATE"]),
                      loss=self.dic_agent_conf["LOSS_FUNCTION"])
        model.summary()
        return model

    def train_network(self):
        learning_rate = float(self.dic_agent_conf["LEARNING_RATE"])
        try:
            self.q_network.optimizer.learning_rate.assign(learning_rate)
        except AttributeError:
            K.set_value(self.q_network.optimizer.learning_rate, learning_rate)

        fine_tune_steps = self.dic_agent_conf.get("FINE_TUNE_STEPS")
        if fine_tune_steps is not None:
            fine_tune_steps = int(fine_tune_steps)
            sample_count = len(self.Y)
            if sample_count == 0:
                print("CoLight: no samples available; skipping fine-tuning")
                return
            batch_size = min(self.dic_agent_conf["BATCH_SIZE"], sample_count)
            final_loss = float("nan")
            for _ in range(fine_tune_steps):
                indices = np.random.choice(
                    sample_count, size=batch_size, replace=False
                )
                batch_x = [np.asarray(value)[indices] for value in self.Xs]
                batch_y = np.asarray(self.Y)[indices]
                result = self.q_network.train_on_batch(batch_x, batch_y)
                final_loss = float(
                    result[0] if isinstance(result, (list, tuple)) else result
                )
            print(
                "CoLight fine-tuning finished, "
                f"updates={fine_tune_steps}, lr={learning_rate:g}, "
                f"loss={final_loss:.6f}, samples={sample_count}"
            )
            return

        sample_count = len(self.Y)
        if sample_count == 0:
            print("CoLight: no samples available; skipping training")
            return

        epochs = self.dic_agent_conf["EPOCHS"]
        batch_size = min(self.dic_agent_conf["BATCH_SIZE"], sample_count)
        # Classic rolling training enables Keras validation only at its configured
        # periodic validation rounds. The intervening rounds still update on all
        # data, but avoid the validation/early-stopping pass. Other callers keep
        # the historical always-validate behaviour by omitting this flag.
        validate_this_round = self.dic_agent_conf.get("RL_VALIDATE_THIS_ROUND", True)
        # Keras cannot split a single sample into non-empty training and
        # validation sets.
        validation_split = 0.3 if validate_this_round and sample_count >= 2 else 0.0
        callbacks = []
        if validation_split:
            callbacks.append(
                EarlyStopping(
                    monitor='val_loss',
                    patience=self.dic_agent_conf["PATIENCE"],
                    verbose=0,
                    mode='min',
                )
            )
        else:
            reason = "one sample available" if sample_count < 2 else "scheduled interval"
            print(f"CoLight: training without validation ({reason})")

        self.q_network.fit(
            self.Xs,
            self.Y,
            batch_size=batch_size,
            epochs=epochs,
            shuffle=False,
            verbose=2,
            validation_split=validation_split,
            callbacks=callbacks,
        )

    def build_network_from_copy(self, network_copy):
        """Initialize a Q network from a copy"""
        network_structure = network_copy.to_json()
        network_weights = network_copy.get_weights()
        network = model_from_json(network_structure, custom_objects=dict(_CUSTOM_OBJECTS))
        network.set_weights(network_weights)
        network.compile(optimizer=Adam(learning_rate=self.dic_agent_conf["LEARNING_RATE"]),
                        loss=self.dic_agent_conf["LOSS_FUNCTION"])

        return network

    def build_network_from_copy_only_weight(self, network, network_copy):
        """Initialize a Q network from a copy"""
        network_weights = network_copy.get_weights()
        network.set_weights(network_weights)
        network.compile(optimizer=Adam(learning_rate=self.dic_agent_conf["LEARNING_RATE"]),
                        loss=self.dic_agent_conf["LOSS_FUNCTION"])
        return network

    def load_network(self, file_name, file_path=None):
        if file_path is None:
            file_path = self.dic_path["PATH_TO_MODEL"]

        # compile=False: Keras 3 cannot re-load the legacy H5 training
        # config's loss/metric functions, so recompile explicitly.
        self.q_network = load_model(
            os.path.join(file_path, "%s.h5" % file_name),
            custom_objects=dict(_CUSTOM_OBJECTS),
            compile=False)
        self.q_network.compile(optimizer=Adam(learning_rate=self.dic_agent_conf["LEARNING_RATE"]),
                               loss=self.dic_agent_conf["LOSS_FUNCTION"])
        print("succeed in loading model %s" % file_name)

    def load_network_bar(self, file_name, file_path=None):
        if file_path is None:
            file_path = self.dic_path["PATH_TO_MODEL"]
        self.q_network_bar = load_model(
            os.path.join(file_path, "%s.h5" % file_name),
            custom_objects=dict(_CUSTOM_OBJECTS),
            compile=False)
        self.q_network_bar.compile(optimizer=Adam(learning_rate=self.dic_agent_conf["LEARNING_RATE"]),
                                   loss=self.dic_agent_conf["LOSS_FUNCTION"])
        print("succeed in loading model %s" % file_name)

    def save_network(self, file_name):
        self.q_network.save(os.path.join(self.dic_path["PATH_TO_MODEL"], "%s.h5" % file_name))

    def save_network_bar(self, file_name):
        self.q_network_bar.save(os.path.join(self.dic_path["PATH_TO_MODEL"], "%s.h5" % file_name))


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


# Named functions used inside Lambda layers: Keras serializes them by
# module-qualified reference (like RepeatVector3D) instead of bytecode, so
# model_from_json/load_model can restore them without the lambda
# deserialization path that Keras 3 cannot shape-infer.
def _adjacency_matmul(x):
    return tf.matmul(x[0], x[1])


def _permute_heads_front(x):
    # [batch,agent,·,h_dim,head]->[batch,agent,head,·,h_dim]
    return K.permute_dimensions(x, (0, 1, 4, 2, 3))


def _softmax_attention(x):
    return K.softmax(tf.matmul(x[0], x[1], transpose_b=True))


def _attention_matmul_mean(x):
    return K.mean(tf.matmul(x[0], x[1]), axis=2)


_CUSTOM_OBJECTS = {
    'RepeatVector3D': RepeatVector3D,
    '_adjacency_matmul': _adjacency_matmul,
    '_permute_heads_front': _permute_heads_front,
    '_softmax_attention': _softmax_attention,
    '_attention_matmul_mean': _attention_matmul_mean,
}
