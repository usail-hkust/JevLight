import os
import sys
import time
import math
import random
import json
import pickle
import subprocess
import shutil
import numpy as np
import pandas as pd
from multiprocessing import Process
from collections import defaultdict
from functools import reduce
from copy import deepcopy

import traci
import sumolib

def _seg_wrap(_name):  # no-op placeholder for the removed profiling hook
        def deco(fn):
            return fn

        return deco


from utils.phase_utils import (
    CANONICAL_CONTROL_PHASES,
    filter_supported_control_phases,
    get_canonical_control_phase,
    split_phase_movements,
)

# Global dictionaries (can be part of config or discovered)
location_dict = {"North": "N", "South": "S", "East": "E", "West": "W"}
location_dict_reverse = {v: k for k, v in location_dict.items()}
direction_dict = {"go_straight": "T", "turn_left": "L", "turn_right": "R"}

# Angles represent the direction of travel (Heading) towards the intersection (calculated via atan2(dy, dx))
angles = [0, math.pi / 2, math.pi, 3 * math.pi / 2, 2 * math.pi]  # Eastbound, Northbound, Westbound, Southbound, Eastbound
# Orients map these Headings to their Origin (Standard Convention)
orients = ['W', 'S', 'E', 'N', 'W', 'S', 'E', 'N']

DEFAULT_YELLOW_TIME = 5


class Intersection:
    """
    Represents a single intersection in the simulation environment, adapted for SUMO.
    Handles state updates, feature calculation, and signal control for this intersection.
    It dynamically discovers its topology from a SUMO network and controls via TraCI.
    """
    _MOVEMENT_TO_PRESSURE_IDX_MAP = {
        'WL': 0, 'WT': 1, 'WR': 2,  # West: Left, Through, Right
        'EL': 3, 'ET': 4, 'ER': 5,  # East: Left, Through, Right
        'NL': 6, 'NT': 7, 'NR': 8,  # North: Left, Through, Right
        'SL': 9, 'ST': 10, 'SR': 11  # South: Left, Through, Right
    }

    def __init__(self, tls_id, dic_traffic_env_conf, traci_conn, sumo_net, path_to_log, adjacency_info,
                 custom_phase_list=None):
        """
        Initializes an Intersection object based on a SUMO traffic light system (TLS).

        Args:
            tls_id (str): The ID of the traffic light system in SUMO.
            dic_traffic_env_conf (dict): The traffic environment configuration dictionary.
            traci_conn (traci.connection): The active TraCI connection object.
            sumo_net (sumolib.net.Net): The pre-parsed sumolib network object.
            path_to_log (str): Path to the directory for logging.
            adjacency_info (dict): Information about neighboring intersections.
            custom_phase_list (list, optional): A list of phase name strings restricting the agent's choices.
        """
        # 1. Store injected dependencies and set compatibility attributes
        self.tls_id = tls_id
        self.inter_id = tls_id
        self.inter_name = tls_id
        self.dic_traffic_env_conf = dic_traffic_env_conf
        self.traci_conn = traci_conn
        self.sumo_net = sumo_net
        self.path_to_log = path_to_log
        self.custom_phase_list = custom_phase_list
        self.adjacency_info = adjacency_info

        # 2. Initial Validation: Ensure the TLS ID is valid
        try:
            if self.tls_id not in self.traci_conn.trafficlight.getIDList():
                raise ValueError(f"TLS ID '{self.tls_id}' not found in the running SUMO simulation.")
        except Exception as e:
            raise ValueError(f"Failed to validate TLS ID '{self.tls_id}': {e}") from e

        # --- Declare attributes that will be populated by _build_conceptual_model ---
        self.virtual = False
        self.point = {}
        self.phases = []  # Raw SUMO phase definitions
        self.control_phases = []  # Final list of phase NAMES available to agent
        self.all_control_phase_names = []  # All detected phase NAMES
        self.phase_name_2_cityflow_idx = {}  # Map name string to actual SUMO phase index
        self.green_phases = []  # List of actual SUMO green phase indices

        self.incoming_roads = {}
        self.outgoing_roads = {}
        self.list_entering_lanes = []  # Padded, canonical lists
        self.list_exiting_lanes = []  # Padded, canonical lists
        self.lane_to_road = {}
        self.list_lanes = []
        self.road_id_2_orient = {}
        self.action_2_phase_index = {}  # action_idx (0,1..) -> SUMO phase_idx
        self.phase_index_2_action_idx = {}
        self.yellow_time = float(
            self.dic_traffic_env_conf.get("YELLOW_TIME", DEFAULT_YELLOW_TIME)
        )
        self.yellow_phase_index = -1
        self.pending_target_phase_index = -1
        self.yellow_start_time = None
        self.is_in_yellow_phase = False

        # 3. Build the conceptual model from SUMO data
        self._build_conceptual_model()
        self._initialize_feature_caches()

        # --- State Variables ---
        self.dic_lane_vehicle_current_step = defaultdict(list)
        self.dic_lane_waiting_vehicle_count_current_step = defaultdict(int)
        self.dic_vehicle_speed_current_step = {}
        self.dic_vehicle_distance_current_step = {}
        self.dic_lane_vehicle_current_step_in = defaultdict(list)
        self.list_lane_vehicle_previous_step_in = []
        self.list_lane_vehicle_current_step_in = []
        self.dic_vehicle_arrive_leave_time = {}

        # --- Feature Storage ---
        self.dic_feature = {}

        # --- Signal Timing ---
        try:
            self._current_sim_time = float(self.traci_conn.simulation.getTime())
        except (traci.TraCIException, TypeError, ValueError):
            self._current_sim_time = 0.0
        self.current_phase_index = 0
        try:
            # Get the initial phase from SUMO
            self.current_phase_index = self.traci_conn.trafficlight.getPhase(self.tls_id)
        except traci.TraCIException as e:
            print(f"Warning: Could not get initial phase for {self.tls_id}. Defaulting to 0. Error: {e}")

        self.default_phase_index = self.current_phase_index
        self.previous_phase_index = self.current_phase_index
        self.next_phase_to_set_index = self.current_phase_index
        self.current_green_phase_index = (
            self.current_phase_index
            if self.current_phase_index in self.green_phases
            else (self.green_phases[0] if self.green_phases else self.default_phase_index)
        )
        self.current_phase_duration = 0
        self.time_since_last_change = 0
        # Armed-duration dedup: adaptive control freezes SUMO's static program
        # by arming setPhaseDuration, but re-arming every simulated second is a
        # redundant TraCI round trip. Track when the armed duration expires so
        # set_signal re-arms only near expiry or after an untracked phase
        # change. None expiry = unknown, forces a re-arm on the next hold.
        self._armed_phase_duration_expiry = None
        self._armed_phase_duration_phase = None

        self.fixed_time_cycle_index = 0

        self.log_file_path = os.path.join(path_to_log, f"signal_{self.inter_name}.txt")
        if self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True):
            with open(self.log_file_path, "w") as f:
                f.write("time,phase_index\n")
            self._log_signal_state()

    def __deepcopy__(self, memo):
        if id(self) in memo:
            return memo[id(self)]

        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result

        for k, v in self.__dict__.items():
            # Skip non-serializable or shared attributes
            if k in ['traci_conn', 'sumo_net', 'incoming_roads', 'outgoing_roads']:
                continue
            setattr(result, k, deepcopy(v, memo))

        result.traci_conn = None
        result.sumo_net = self.sumo_net
        result.incoming_roads = self.incoming_roads.copy()
        result.outgoing_roads = self.outgoing_roads.copy()

        return result

    def _build_conceptual_model(self):
        """
        Orchestrates the discovery of intersection topology (lanes, roads, orientations)
        and traffic light logic (phases, movements) from the SUMO simulation.
        """
        # Get basic intersection info from the pre-parsed network object
        try:
            tls_node = self.sumo_net.getNode(self.tls_id)
            self.point = {"x": tls_node.getCoord()[0], "y": tls_node.getCoord()[1]}
        except KeyError:
            # Fallback if TLS node is not found in the static network file
            self.point = {"x": 0, "y": 0}

        # Step 1: Discover all connected lanes and roads
        self._discover_lanes_and_roads()

        # Step 2: Determine road orientations based on geometry
        self._calculate_road_orientations()

        # Step 3: Build the legacy `road_links` structure.
        self._build_road_links()

        # Step 4: Create padded, canonical lane lists for feature calculation.
        self._create_canonical_lane_lists()

        # Step 5: Discover SUMO phases and map them to canonical names
        self._discover_phases_and_movements()

        # Step 6: Apply custom phase filtering if provided.
        self._apply_custom_phase_mapping()

    def _print_intersection_debug_info(self, intersection_obj):
        """
        打印指定Intersection对象的详细调试信息，包括相位和车道方向。
        """
        inter_id = intersection_obj.inter_id
        print("\n" + "=" * 80)
        print(f"DEBUG INFO FOR INTERSECTION: {inter_id}")
        print("=" * 80)

        # 1. 打印可控的信号灯相位名称
        #    这对应您问题中的 ['SL', 'WT']
        print("\n[1] 可用信号灯相位 (Control Phases):")
        if intersection_obj.control_phases:
            print(f"    {intersection_obj.control_phases}")
        else:
            print("    - No control phases found.")

        # 2. 打印入口和出口道路的地理方向 (东/南/西/北)
        print("\n[2] 道路地理方向 (Road Orientations):")
        print("  入口道路 (Incoming):")
        if intersection_obj.road_id_2_orient.get('incoming'):
            for road, orient in intersection_obj.road_id_2_orient['incoming'].items():
                print(f"    - Road '{road}': {orient} approach")
        else:
            print("    - None found.")

        print("\n  出口道路 (Outgoing):")
        if intersection_obj.road_id_2_orient.get('outgoing'):
            for road, orient in intersection_obj.road_id_2_orient['outgoing'].items():
                print(f"    - Road '{road}': {orient} exit")
        else:
            print("    - None found.")

        # 3. 打印解析出的具体车道转向信息
        #    这详细说明了从哪条路到哪条路是什么转向
        print("\n[3] 解析出的车道转向 (Parsed Lane Movements / Road Links):")
        if intersection_obj.road_links:
            for link in intersection_obj.road_links:
                start_road = link.get('startRoad')
                end_road = link.get('endRoad')
                turn_type = link.get('type')
                print(f"  - FROM '{start_road}' TO '{end_road}', Turn: {turn_type}")
        else:
            print("    - No road links found.")

        print("=" * 80 + "\n")

    def _discover_lanes_and_roads(self):
        """
        Populates lane and road lists using TraCI and the sumolib network object.
        """
        # Get all lanes controlled by this traffic light
        try:
            # Note: getControlledLanes returns ALL lanes, including internal ones.
            self.list_entering_lanes = list(set(self.traci_conn.trafficlight.getControlledLanes(self.tls_id)))
        except traci.TraCIException as e:
            print(f"Warning: Could not get controlled lanes for {self.tls_id}. Error: {e}")
            self.list_entering_lanes = []
            return

        if not self.list_entering_lanes:
            return

        # Discover incoming/outgoing roads and all lanes
        temp_outgoing_lanes = set()

        for lane_id in self.list_entering_lanes:
            try:
                lane_obj = self.sumo_net.getLane(lane_id)
                road_obj = lane_obj.getEdge()
                road_id = road_obj.getID()

                # Ignore internal edges
                if not road_id.startswith(":"):
                    self.incoming_roads[road_id] = road_obj
                    self.lane_to_road[lane_id] = road_id

                # Find corresponding outgoing lanes from this incoming lane (sumolib)
                outgoing_lanes = lane_obj.getOutgoingLanes()  # list[sumolib.net.Lane]

                for outgoing_lane in outgoing_lanes:
                    outgoing_lane_id = outgoing_lane.getID()
                    outgoing_road_obj = outgoing_lane.getEdge()
                    outgoing_road_id = outgoing_road_obj.getID()

                    # Ensure it's not an internal junction edge
                    if not outgoing_road_id.startswith(":"):
                        temp_outgoing_lanes.add(outgoing_lane_id)
                        self.outgoing_roads[outgoing_road_id] = outgoing_road_obj
                        self.lane_to_road[outgoing_lane_id] = outgoing_road_id
            except (KeyError, AttributeError) as e:
                pass

        self.list_exiting_lanes = sorted(list(temp_outgoing_lanes))
        self.list_lanes = sorted(list(set(self.list_entering_lanes + self.list_exiting_lanes)))

    def _calculate_road_orientations(self):
        """
        Calculates and assigns canonical orientations (N, S, E, W) to incoming and
        outgoing roads based on their geometry from the sumolib network.
        """

        def _calculate_for(roads_dict, is_incoming):
            center_x, center_y = self.point['x'], self.point['y']
            roads_with_angle = []

            for road_id, road_obj in roads_dict.items():
                shape = road_obj.getShape()
                if len(shape) < 2:
                    continue

                point_x, point_y = shape[-2] if is_incoming else shape[1]

                dx = center_x - point_x
                dy = center_y - point_y
                angle = math.atan2(dy, dx)
                if angle < 0: angle += 2 * math.pi

                # Find the closest cardinal direction
                orient_angle_diffs = np.abs(np.subtract(angles, angle))
                orient_index = np.argmin(orient_angle_diffs)
                orient = orients[orient_index]
                orient_angle_diff = orient_angle_diffs[orient_index]

                roads_with_angle.append(
                    {'id': road_id, 'angle': angle, 'orient': orient, 'angle_diff': orient_angle_diff}
                )

            if not roads_with_angle:
                return {}

            roads_with_angle.sort(key=lambda x: x['angle'])
            # Use the min angle diff for starting point
            min_orient_road = min(roads_with_angle, key=lambda x: x['angle_diff'])
            min_orient_road_index = roads_with_angle.index(min_orient_road)
            roads_with_angle = roads_with_angle[min_orient_road_index:] + roads_with_angle[:min_orient_road_index]

            if not self._decide_road_orient(roads_with_angle):
                # 即使失败，也返回初始的方向分配
                return {road['id']: road.get('orient') for road in roads_with_angle}

            result = {road['id']: road.get('orient') for road in roads_with_angle}
            return result

        self.road_id_2_orient['incoming'] = _calculate_for(self.incoming_roads, is_incoming=True)
        self.road_id_2_orient['outgoing'] = _calculate_for(self.outgoing_roads, is_incoming=False)

    def _build_road_links(self):
        """
        Builds the `road_links` structure by relying on SUMO's connection definitions (via sumolib)
        """
        self.road_links = []
        links_grouped = defaultdict(list)

        try:
            controlled_links = self.traci_conn.trafficlight.getControlledLinks(self.tls_id)
        except traci.TraCIException as e:
            print(f"Warning: getControlledLinks failed for {self.tls_id}: {e}")
            return

        # Mapping SUMO internal directions ('s', 'l', 'r', etc.) to standardized turn types
        SUMO_DIR_MAP = {
            's': 'go_straight',
            't': 'turn_left',  # 't' (turn) is often treated as slight left/through
            'l': 'turn_left',
            'L': 'turn_left',
            'r': 'turn_right',
            'R': 'turn_right',
        }

        for link_group in controlled_links:
            if not link_group:
                continue
            from_lane_id, to_lane_id, _via = link_group[0]

            if from_lane_id.startswith(":") or to_lane_id.startswith(":"):
                continue

            try:
                from_lane_obj = self.sumo_net.getLane(from_lane_id)
                to_lane_obj = self.sumo_net.getLane(to_lane_id)
                from_road_id = from_lane_obj.getEdge().getID()
                to_road_id = to_lane_obj.getEdge().getID()

                # Find the specific connection object between these two lanes in sumolib
                connection = None
                for conn in from_lane_obj.getOutgoing():
                    if conn.getToLane() == to_lane_obj:
                        connection = conn
                        break

                if connection is None:
                    continue

                # Get the direction attribute from the connection
                sumo_direction = connection.getDirection()
                turn_type = SUMO_DIR_MAP.get(sumo_direction)

                if turn_type is None:
                    continue  # Skip unknown/unsupported types (e.g., U-turns 'u')

                # We still need the orientation (now correctly calculated) to categorize the movement
                f_or = self.road_id_2_orient['incoming'].get(from_road_id)

                if not f_or:
                    continue

                start_lane_idx = from_lane_obj.getIndex()
                end_lane_idx = to_lane_obj.getIndex()

                links_grouped[(from_road_id, to_road_id, turn_type)].append({
                    "startLaneIndex": start_lane_idx,
                    "endLaneIndex": end_lane_idx
                })

            except (KeyError, AttributeError) as e:
                continue

        for (start_road, end_road, turn_type), lane_links in links_grouped.items():
            # Remove duplicate lane links and sort for stability
            unique_lane_links = [dict(t) for t in {tuple(d.items()) for d in lane_links}]
            # Sort by startLaneIndex primarily for consistency
            unique_lane_links.sort(key=lambda x: (x['startLaneIndex'], x.get('endLaneIndex', -1)))
            self.road_links.append({
                "startRoad": start_road,
                "endRoad": end_road,
                "type": turn_type,
                "laneLinks": unique_lane_links
            })

    def _create_canonical_lane_lists(self):
        """
        Creates 12-element, canonically ordered (W,E,N,S approach, 3 lanes each)
        lists for entering and exiting lanes. Non-existent lanes are filled with None.
        This is required for compatibility with feature calculation methods that expect a fixed-size input.
        """
        # Ensure we have a valid road_id_2_orient map
        if not self.road_id_2_orient or not 'incoming' in self.road_id_2_orient:
            print(
                f"Warning: {self.inter_id} Missing orientation data for canonical lane list creation. Using default empty lists.")
            self.list_entering_lanes = [None] * 12
            self.list_exiting_lanes = [None] * 12
            return

        padded_entering_lanes = [None] * 12
        padded_exiting_lanes = [None] * 12

        # --- Pad Entering Lanes ---
        lanes_by_orient = defaultdict(list)
        for road_id, orient in self.road_id_2_orient.get('incoming', {}).items():
            road_obj = self.incoming_roads.get(road_id)
            if road_obj:
                for lane_obj in road_obj.getLanes():
                    lanes_by_orient[orient].append(lane_obj.getID())

        orient_map = {'W': 0, 'E': 3, 'N': 6, 'S': 9}
        for orient, offset in orient_map.items():
            lanes = sorted(lanes_by_orient.get(orient, []))
            for i in range(3):
                if i < len(lanes):
                    padded_entering_lanes[offset + i] = lanes[i]

        # --- Pad Exiting Lanes ---
        exiting_lanes_by_orient = defaultdict(list)
        for road_id, orient in self.road_id_2_orient.get('outgoing', {}).items():
            road_obj = self.outgoing_roads.get(road_id)
            if road_obj:
                for lane_obj in road_obj.getLanes():
                    exiting_lanes_by_orient[orient].append(lane_obj.getID())

        for orient, offset in orient_map.items():
            lanes = sorted(exiting_lanes_by_orient.get(orient, []))
            for i in range(3):
                if i < len(lanes):
                    padded_exiting_lanes[offset + i] = lanes[i]

        # Overwrite the instance attributes with the padded, canonical lists
        self.list_entering_lanes = padded_entering_lanes
        self.list_exiting_lanes = padded_exiting_lanes

        # Update the list_lanes to include all padded lanes
        self.list_lanes = self.list_entering_lanes + self.list_exiting_lanes

        # Remove None values from the list_lanes
        self.list_lanes = [lane for lane in self.list_lanes if lane is not None]

    def _discover_phases_and_movements(self):
        """
        Discovers the traffic light program from SUMO, identifies green phases,
        and translates them into canonical movement-based names (e.g., "ETWT")
        by READING THE PHASE NAME ATTRIBUTE.
        """
        try:
            # Get the first (active) program definition
            logic = self.traci_conn.trafficlight.getCompleteRedYellowGreenDefinition(self.tls_id)[0]
            self.phases = logic.getPhases()
        except (traci.TraCIException, IndexError) as e:
            print(f"Warning: Could not get TLS logic for '{self.tls_id}'. Phase control disabled. Error: {e}")
            return

        phase_dict = {}  # cityflow_idx -> set(movement_names_like_WT)
        phase_name_to_idx_map = {}
        temp_control_phase_names = []

        for phase_idx, phase in enumerate(self.phases):
            phase_name_str = phase.name
            if phase_name_str == "YELLOW_ALL_RED":
                if self.yellow_phase_index == -1:
                    self.yellow_phase_index = phase_idx
                    print(
                        f"Found first YELLOW_ALL_RED phase for {self.tls_id}: "
                        f"index={phase_idx}, network_duration={phase.duration}s, "
                        f"controlled_duration={self.yellow_time}s"
                    )
                continue

            # A phase is green if it has a 'G' or 'g' and is not a short transition phase.
            if ('G' in phase.state or 'g' in phase.state) and phase.minDur > 2:
                self.green_phases.append(phase_idx)
                # 1. Read the phase name directly from the object. This is the name
                #    set by convert_sumo_roadnet_phases.py script.
                # phase_name_str already set above

                # 2. Skip phases that are unnamed.
                #    This makes the logic robust and ignores transitional phases.
                if not phase_name_str:
                    continue

                # 3. Create a set of movements from the name for the legacy `phase_dict`
                #    This assumes names are pairs of characters, e.g., "ETWT" -> {"ET", "WT"}
                movement_names = set()
                if len(phase_name_str) % 2 == 0:
                    for i in range(0, len(phase_name_str), 2):
                        movement_names.add(phase_name_str[i:i + 2])

                if not movement_names:
                    continue

                phase_dict[phase_idx] = movement_names

                # 4. Use the clean, correct name for agent control.
                if phase_name_str not in phase_name_to_idx_map:
                    temp_control_phase_names.append(phase_name_str)
                    phase_name_to_idx_map[phase_name_str] = phase_idx

        self.phase_index_2_phase_name = phase_dict
        self.all_control_phase_names = sorted(list(set(temp_control_phase_names)))
        print(f'self.all_control_phase_names: {self.all_control_phase_names}')
        self.phase_name_2_cityflow_idx = phase_name_to_idx_map
        if self.green_phases:
            # Set a reasonable default green phase
            if self.all_control_phase_names:
                first_phase_name = self.all_control_phase_names[0]
                self.default_phase_index = self.phase_name_2_cityflow_idx.get(first_phase_name, self.green_phases[0])
            else:
                self.default_phase_index = self.green_phases[0]

    # Helper methods for road orientation calculation (used in _calculate_road_orientations)
    def _get_opposite_road(self, cur_road, roads_with_angle, orients_taken={}):
        """
        Finds the opposite road for a given road based on its orientation.
        """
        for orient, road_idx in orients_taken.items():
            road = roads_with_angle[road_idx]
            if road['orient'] and cur_road['id'] != road['id'] and abs(
                    abs(cur_road['angle'] - road['angle']) - math.pi) < math.pi / 8:
                return road_idx
        return -1

    def _decide_road_orient(self, roads_with_angle, last_road=None, orients_taken={}, cur_index=0):
        if cur_index == len(roads_with_angle):
            return True

        cur_road = roads_with_angle[cur_index]

        my_possible_orients = []
        cur_possible_dir_index = 0 if last_road is None else (orients.index(last_road['orient']) + 1)
        for i in range(cur_possible_dir_index, cur_possible_dir_index + 4):
            if orients[i % 4] in orients_taken or (not last_road is None and orients[i % 4] == last_road['orient']):
                break
            my_possible_orients.append(orients[i % 4])

        if len(my_possible_orients) == 0:
            return False

        my_fav_orient_index = my_possible_orients.index(cur_road['orient']) if cur_road[
                                                                                   'orient'] in my_possible_orients else 0
        opposite_road_index = self._get_opposite_road(cur_road, roads_with_angle, orients_taken)
        if opposite_road_index != -1:
            my_fav_orient_index = my_possible_orients.index(
                orients[(orients.index(roads_with_angle[opposite_road_index]['orient']) + 2) % 4])
        my_possible_orients = my_possible_orients[my_fav_orient_index:] + my_possible_orients[:my_fav_orient_index]

        for dir in my_possible_orients:
            cur_road['orient'] = dir
            _orients_taken = orients_taken.copy()
            _orients_taken[dir] = cur_index
            if self._decide_road_orient(roads_with_angle, cur_road, _orients_taken, cur_index + 1):
                return True

        return False

    def _apply_custom_phase_mapping(self):
        """
        Filters the detected phases based on self.custom_phase_list.
        Sets the final self.control_phases and self.action_2_phase_index.
        """
        source_phase_names = self.all_control_phase_names
        name_to_idx_map = self.phase_name_2_cityflow_idx
        final_control_phase_names = []

        if self.custom_phase_list is not None:
            available_names_set = set(source_phase_names)
            custom_control_phase_names = []
            for name in self.custom_phase_list:
                if name in available_names_set:
                    if name not in custom_control_phase_names:
                        custom_control_phase_names.append(name)
                else:
                    print(f"  Warning: Custom phase '{name}' not found in detected phases {source_phase_names}.")
            final_control_phase_names = filter_supported_control_phases(custom_control_phase_names)

        else:
            final_control_phase_names = filter_supported_control_phases(source_phase_names)

        if not final_control_phase_names and self.green_phases:
            print(final_control_phase_names, self.green_phases)
            print(
                f"Intersection {self.inter_id}: No supported four-phase control phases detected.")
            final_control_phase_names = []

        self.control_phases = final_control_phase_names
        self.action_2_phase_index = {}
        self.phase_index_2_action_idx = {}
        allowed_sumo_indices = set()

        for i, phase_name in enumerate(self.control_phases):
            sumo_idx = name_to_idx_map.get(phase_name)
            if sumo_idx is not None:
                self.action_2_phase_index[i] = sumo_idx
                self.phase_index_2_action_idx[sumo_idx] = i
                allowed_sumo_indices.add(sumo_idx)

        original_green_phases = list(self.green_phases)
        self.green_phases = [idx for idx in original_green_phases if idx in allowed_sumo_indices]

    def _initialize_feature_caches(self):
        """Cache static lane and phase mappings used by every simulation step."""
        self._entering_lane_index = {
            lane_id: lane_idx
            for lane_idx, lane_id in enumerate(self.list_entering_lanes)
            if lane_id is not None
        }

        exiting_indices_by_orient = defaultdict(list)
        for lane_idx, lane_id in enumerate(self.list_exiting_lanes):
            if lane_id is None:
                continue
            road_id = self.lane_to_road.get(lane_id)
            orient = self.road_id_2_orient.get("outgoing", {}).get(road_id)
            if orient:
                exiting_indices_by_orient[orient].append(lane_idx)

        conceptual_slots = [
            ("W", "L", "turn_left"),
            ("W", "T", "go_straight"),
            ("W", "R", "turn_right"),
            ("E", "L", "turn_left"),
            ("E", "T", "go_straight"),
            ("E", "R", "turn_right"),
            ("N", "L", "turn_left"),
            ("N", "T", "go_straight"),
            ("N", "R", "turn_right"),
            ("S", "L", "turn_left"),
            ("S", "T", "go_straight"),
            ("S", "R", "turn_right"),
        ]
        destination_orient = {
            ("W", "L"): "S", ("W", "T"): "E", ("W", "R"): "N",
            ("E", "L"): "N", ("E", "T"): "W", ("E", "R"): "S",
            ("N", "L"): "W", ("N", "T"): "S", ("N", "R"): "E",
            ("S", "L"): "E", ("S", "T"): "N", ("S", "R"): "W",
        }

        pressure_index_cache = []
        incoming_orients = self.road_id_2_orient.get("incoming", {})
        for orient, turn_char, turn_type in conceptual_slots:
            entering_indices = []
            for road_link in self.road_links:
                start_road_id = road_link.get("startRoad")
                if (
                    not start_road_id
                    or road_link.get("type") != turn_type
                    or incoming_orients.get(start_road_id) != orient
                ):
                    continue
                for lane_link_detail in road_link.get("laneLinks", []):
                    lane_idx = lane_link_detail.get("startLaneIndex")
                    if lane_idx is None:
                        continue
                    full_lane_id = f"{start_road_id}_{lane_idx}"
                    master_idx = self._entering_lane_index.get(full_lane_id)
                    if master_idx is not None:
                        entering_indices.append(master_idx)

            outgoing_orient = destination_orient.get((orient, turn_char))
            pressure_index_cache.append((
                tuple(entering_indices),
                tuple(exiting_indices_by_orient.get(outgoing_orient, ())),
            ))

        self._pressure_index_cache = tuple(pressure_index_cache)
        self._four_phase_cache = self._build_four_phase_mapping()

        # CityLight's official observation groups waiting vehicles by signal
        # phase.  Keep the exact participating lane sets rather than rebuilding
        # them from padded lane positions in the policy.
        turn_type_by_code = {
            "L": "turn_left",
            "T": "go_straight",
        }
        self._citylight_phase_lane_indices = []
        self._citylight_phase_lanes = []
        for phase_name in CANONICAL_CONTROL_PHASES:
            entering_indices = set()
            entering_lanes = set()
            exiting_lanes = set()
            for movement in split_phase_movements(phase_name):
                if len(movement) != 2:
                    continue
                approach, movement_code = movement
                turn_type = turn_type_by_code.get(movement_code)
                if turn_type is None:
                    continue
                for road_link in self.road_links:
                    start_road = road_link.get("startRoad")
                    if (
                        road_link.get("type") != turn_type
                        or self.road_id_2_orient.get("incoming", {}).get(start_road)
                        != approach
                    ):
                        continue
                    end_road = road_link.get("endRoad")
                    for lane_link in road_link.get("laneLinks", []):
                        start_lane = f"{start_road}_{lane_link['startLaneIndex']}"
                        end_lane = f"{end_road}_{lane_link['endLaneIndex']}"
                        master_index = self._entering_lane_index.get(start_lane)
                        if master_index is not None:
                            entering_indices.add(master_index)
                            entering_lanes.add(start_lane)
                        exiting_lanes.add(end_lane)
            self._citylight_phase_lane_indices.append(tuple(sorted(entering_indices)))
            self._citylight_phase_lanes.append(
                (tuple(sorted(entering_lanes)), tuple(sorted(exiting_lanes)))
            )

        self.citylight_graph_info = {
            "indices": [0, 0, 0, 0],
            "mask": [0.0, 0.0, 0.0, 0.0],
            "types": [0.0, 0.0, 0.0, 0.0],
            "relations": [[0.0, 0.0] for _ in range(4)],
            "distances": [[0.0, 0.0] for _ in range(4)],
        }

    def _log_signal_state(self):
        """Logs the current time and phase index."""
        if not self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True):
            return
        try:
            current_time = self.get_current_time()
            with open(self.log_file_path, "a") as f:
                f.write(f"{current_time},{self.current_phase_index}\n")
        except Exception as e:
            print(f"Error logging signal state for {self.inter_name}: {e}")

    def set_signal(self, action):
        """Apply one second of a synchronous green/yellow control cycle."""
        if not self.phases:
            return

        if self.is_in_yellow_phase:
            elapsed = self.get_current_time() - self.yellow_start_time
            if elapsed >= self.yellow_time:
                target_phase_index = self.pending_target_phase_index
                try:
                    self.traci_conn.trafficlight.setPhase(
                        self.tls_id,
                        target_phase_index,
                    )
                    self.traci_conn.trafficlight.setPhaseDuration(
                        self.tls_id,
                        self.dic_traffic_env_conf.get("GREEN_TIME", 10),
                    )
                    self._armed_phase_duration_expiry = (
                        self.get_current_time()
                        + self.dic_traffic_env_conf.get("GREEN_TIME", 10)
                    )
                    self._armed_phase_duration_phase = target_phase_index
                    self.previous_phase_index = self.current_phase_index
                    self.current_phase_index = target_phase_index
                    self.current_green_phase_index = target_phase_index
                    self.next_phase_to_set_index = target_phase_index
                    self.current_phase_duration = 0
                    self.time_since_last_change = 0
                    self.pending_target_phase_index = -1
                    self.yellow_start_time = None
                    self.is_in_yellow_phase = False
                    self._log_signal_state()
                except traci.TraCIException as e:
                    print(
                        f"TraCIException switching from yellow to phase "
                        f"{target_phase_index} for {self.inter_name}. Error: {e}"
                    )
            return

        target_phase_index = -1
        self.time_since_last_change += 1

        if action == -1:
            target_phase_index = self.current_green_phase_index
        elif not self.control_phases or not self.action_2_phase_index:
            target_phase_index = self.current_green_phase_index
        elif action >= 0:
            num_actions = len(self.control_phases)
            if num_actions > 0:
                actual_action_index = action % num_actions
                default_sumo_idx = self.action_2_phase_index.get(
                    0,
                    self.current_green_phase_index,
                )
                target_phase_index = self.action_2_phase_index.get(actual_action_index, default_sumo_idx)
            else:
                target_phase_index = self.current_green_phase_index
        else:
            target_phase_index = self.current_green_phase_index

        if target_phase_index == -1:
            return

        if target_phase_index == self.current_green_phase_index:
            # Adaptive control owns phase timing. Refreshing the remaining
            # duration prevents SUMO's static program from advancing itself.
            # One armed duration already freezes the phase until it expires,
            # so re-arm only near expiry (2s safety margin) or when the cache
            # no longer describes this phase — not on every simulated second.
            interval = self.dic_traffic_env_conf.get("INTERVAL", 1.0)
            min_action_time = self.dic_traffic_env_conf.get("MIN_ACTION_TIME", 15)
            rearm_needed = (
                self._armed_phase_duration_expiry is None
                or (self._armed_phase_duration_expiry - self.get_current_time())
                <= 2 * interval
                or self._armed_phase_duration_phase != target_phase_index
            )
            if rearm_needed:
                try:
                    self.traci_conn.trafficlight.setPhaseDuration(
                        self.tls_id,
                        min_action_time,
                    )
                except traci.TraCIException as e:
                    print(
                        f"TraCIException holding phase {target_phase_index} "
                        f"for {self.inter_name}. Error: {e}"
                    )
                    return
                self._armed_phase_duration_expiry = (
                    self.get_current_time() + min_action_time
                )
                self._armed_phase_duration_phase = target_phase_index
            return

        try:
            if self.yellow_phase_index != -1:
                self.pending_target_phase_index = target_phase_index
                self.next_phase_to_set_index = target_phase_index
                self.yellow_start_time = self.get_current_time()
                self.is_in_yellow_phase = True
                self.previous_phase_index = self.current_phase_index
                self.current_phase_index = self.yellow_phase_index
                self.current_phase_duration = 0
                self.traci_conn.trafficlight.setPhase(
                    self.tls_id,
                    self.yellow_phase_index,
                )
                self.traci_conn.trafficlight.setPhaseDuration(
                    self.tls_id,
                    self.yellow_time,
                )
                self._armed_phase_duration_expiry = (
                    self.get_current_time() + self.yellow_time
                )
                self._armed_phase_duration_phase = self.yellow_phase_index
                self._log_signal_state()
            else:
                print(
                    f"Warning: No YELLOW_ALL_RED phase found for {self.tls_id}; "
                    f"switching directly to phase {target_phase_index}."
                )
                self.traci_conn.trafficlight.setPhase(
                    self.tls_id,
                    target_phase_index,
                )
                # No duration is armed on this path; SUMO applies the static
                # program's own duration, so the next hold must re-arm.
                self._armed_phase_duration_expiry = None
                self._armed_phase_duration_phase = None
                self.previous_phase_index = self.current_phase_index
                self.current_phase_index = target_phase_index
                self.current_green_phase_index = target_phase_index
                self.next_phase_to_set_index = target_phase_index
                self.current_phase_duration = 0
                self.time_since_last_change = 0
                self._log_signal_state()
        except traci.TraCIException as e:
            print(
                f"TraCIException setting phase {target_phase_index} "
                f"for {self.inter_name}. Error: {e}"
            )

    def update_previous_measurements(self):
        """Copies current measurements to previous step's variables."""
        self.previous_phase_index = self.current_phase_index
        self.list_lane_vehicle_previous_step_in = self.list_lane_vehicle_current_step_in[:]

    def update_current_measurements(self, simulator_state, full_feature_update=True):
        """
        Updates intersection state based on the global simulator state.
        Calculates features for the current step.
        """
        # --- Update Phase Duration and Sync Current Phase ---
        self._current_sim_time = float(
            simulator_state.get("current_time", self._current_sim_time)
        )
        subscribed_phases = simulator_state.get("get_trafficlight_phase", {})
        subscribed_phase = subscribed_phases.get(self.tls_id)
        if subscribed_phase is not None:
            self.current_phase_index = int(subscribed_phase)
        else:
            try:
                self.current_phase_index = self.traci_conn.trafficlight.getPhase(self.tls_id)
            except traci.TraCIException as e:
                print(f"Warning: Could not sync phase index for {self.tls_id}. Error: {e}")

        if self.current_phase_index == self.previous_phase_index:
            self.current_phase_duration += 1
        else:
            self.current_phase_duration = 1

        # --- Update Vehicle/Lane States ---
        # These global dictionaries are rebuilt by SUMOEnv every step and are
        # read-only here. Sharing them avoids one full-network copy per junction.
        self.dic_lane_vehicle_current_step = simulator_state["get_lane_vehicles"]
        self.dic_lane_waiting_vehicle_count_current_step = simulator_state[
            "get_lane_waiting_vehicle_count"]
        self.dic_vehicle_speed_current_step = simulator_state["get_vehicle_speed"]
        self.dic_vehicle_distance_current_step = simulator_state["get_vehicle_distance"]

        if self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True) and (
            full_feature_update
            or not self.dic_traffic_env_conf.get(
                "BOUNDARY_FEATURES_IN_DETAILED_MODE", False
            )
        ):
            # Per-intersection vehicle trajectories back RLLight's legacy
            # analysis artifacts. AutoAgent uses SUMOEnv's global canonical
            # vehicle counters, so it does not need these repeated set scans.
            # In the boundary tier this runs only on decision-boundary
            # seconds; vehicle_*.csv enter/leave times coarsen accordingly
            # (no in-repo reader) and nothing else consumes the in-sets.
            self.dic_lane_vehicle_current_step_in = defaultdict(list)
            for lane_id in self.list_entering_lanes:
                if lane_id is not None:
                    self.dic_lane_vehicle_current_step_in[lane_id] = (
                        self.dic_lane_vehicle_current_step.get(lane_id, [])
                    )

            current_vehicles_in = set()
            for vehicles in self.dic_lane_vehicle_current_step_in.values():
                current_vehicles_in.update(vehicles)
            self.list_lane_vehicle_current_step_in = list(current_vehicles_in)

            previous_vehicles_in = set(self.list_lane_vehicle_previous_step_in)
            list_vehicle_new_arrive = list(
                current_vehicles_in - previous_vehicles_in
            )
            list_vehicle_new_left = list(
                previous_vehicles_in - current_vehicles_in
            )
            self._update_arrive_time(
                list_vehicle_new_arrive, self._current_sim_time
            )
            self._update_left_time(
                list_vehicle_new_left, self._current_sim_time
            )
        elif not self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True):
            self.dic_lane_vehicle_current_step_in = {}
            self.list_lane_vehicle_current_step_in = []
        # else: boundary-tier mid-window seconds keep the last boundary's
        # in-sets, so the next boundary's diff is against the previous
        # boundary (vehicle_*.csv coarsens to boundary resolution).

        # --- Update Features ---
        self._update_feature(minimal=not full_feature_update)

    def _update_arrive_time(self, list_vehicle_arrive, timestamp=None):
        """Records the arrival time for vehicles entering the intersection's approach lanes."""
        ts = self.get_current_time() if timestamp is None else timestamp
        for vehicle in list_vehicle_arrive:
            if vehicle not in self.dic_vehicle_arrive_leave_time:
                self.dic_vehicle_arrive_leave_time[vehicle] = {"enter_time": ts, "leave_time": np.nan}

    def _update_left_time(self, list_vehicle_left, timestamp=None):
        """Records the departure time for vehicles leaving the intersection's approach lanes."""
        ts = self.get_current_time() if timestamp is None else timestamp
        for vehicle in list_vehicle_left:
            if vehicle in self.dic_vehicle_arrive_leave_time:
                if np.isnan(self.dic_vehicle_arrive_leave_time[vehicle]["leave_time"]):
                    self.dic_vehicle_arrive_leave_time[vehicle]["leave_time"] = ts

    def _build_four_phase_mapping(self):
        """Build the stable local/canonical phase mapping."""
        available_phases = self.control_phases
        filtered_2_eight = {}
        eight_2_filtered = {}
        # Use a dictionary to store phases by their default index
        phase_dict = {}

        for idx, phase in enumerate(available_phases):
            canonical_phase = get_canonical_control_phase(phase)
            if canonical_phase is None:
                continue

            f_idx = CANONICAL_CONTROL_PHASES.index(canonical_phase)
            if f_idx not in filtered_2_eight:
                filtered_2_eight[f_idx] = idx
                eight_2_filtered[idx] = f_idx
                phase_dict[f_idx] = phase

        # Build filtered_phases in the order of CANONICAL_CONTROL_PHASES
        filtered_phases = [phase_dict[f_idx] for f_idx in sorted(phase_dict.keys())]

        return filtered_2_eight, eight_2_filtered, filtered_phases

    def _get_four_phase(self):
        """Get the cached control-phase mapping for this intersection."""
        return self._four_phase_cache

    def _update_feature(self, minimal=False):
        """Calculates and stores various state features for the current time step.

        ``minimal=True`` computes only the per-second statistics fields
        (phase bookkeeping + entering-lane queue); the remaining
        control-observation fields are refreshed at decision boundaries via
        ``update_current_measurements(full_feature_update=True)``. Ignored in
        detailed-logging mode, whose legacy per-second logs read everything.
        """
        dic_feature = {}

        # --- Basic Features ---
        active_phase_index = self.current_phase_index
        dic_feature["cur_phase"] = [active_phase_index]
        cur_action = self.phase_index_2_action_idx.get(
            self.current_green_phase_index,
            0,
        )
        dic_feature['cur_phase_four'] = [self._four_phase_cache[1].get(cur_action, 0)]
        dic_feature["time_this_phase"] = [self.current_phase_duration]  # Time in current phase (including transition)

        # Use the padded lists for feature calculation (handles non-existent lanes with None)
        dic_feature["lane_num_waiting_vehicle_in"] = [
            self.dic_lane_waiting_vehicle_count_current_step.get(lane, 0) if lane is not None else 0
            for lane in self.list_entering_lanes
        ]

        if minimal and (
            not self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True)
            or self.dic_traffic_env_conf.get(
                "BOUNDARY_FEATURES_IN_DETAILED_MODE", False
            )
        ):
            if self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True):
                # Detailed-boundary tier (RLLight pipeline): mid-window seconds
                # keep exactly the fields ConstructSample's per-second reward
                # average reads - lane_num_waiting_vehicle_in (queue_length)
                # and pressure (|sum| of the waiting_in + negated waiting_out
                # list) - so the training samples stay bit-identical while the
                # segment/citylight/movement features refresh once per
                # decision boundary.
                dic_feature["lane_num_waiting_vehicle_out"] = [
                    self.dic_lane_waiting_vehicle_count_current_step.get(lane, 0) if lane is not None else 0
                    for lane in self.list_exiting_lanes
                ]
                dic_feature["pressure"] = dic_feature["lane_num_waiting_vehicle_in"] + [
                    -count for count in dic_feature["lane_num_waiting_vehicle_out"]
                ]
                self.dic_feature = dic_feature
                return
            # Mid-window seconds on the lightweight AutoAgent path: the only
            # per-second feature reader is the canonical queue accumulation,
            # which consumes lane_num_waiting_vehicle_in. Everything else is
            # control-observation state, refreshed at decision boundaries.
            self.dic_feature = dic_feature
            return

        dic_feature["lane_num_vehicle"] = [
            len(self.dic_lane_vehicle_current_step.get(lane, [])) if lane is not None else 0
            for lane in self.list_entering_lanes
        ]
        dic_feature["lane_num_vehicle_downstream"] = [
            len(self.dic_lane_vehicle_current_step.get(lane, [])) if lane is not None else 0
            for lane in self.list_exiting_lanes
        ]
        dic_feature["lane_num_waiting_vehicle_out"] = [
            self.dic_lane_waiting_vehicle_count_current_step.get(lane, 0) if lane is not None else 0
            for lane in self.list_exiting_lanes
        ]

        # Pressure calculated based on actual lane counts
        dic_feature["pressure"] = dic_feature["lane_num_waiting_vehicle_in"] + [-count for count in dic_feature[
            "lane_num_waiting_vehicle_out"]]

        # Calculate pressures using the helper methods that assume 12 lanes / specific turn mappings
        dic_feature["traffic_movement_pressure_queue"] = self._get_traffic_movement_pressure_general(
            dic_feature["lane_num_waiting_vehicle_in"], dic_feature["lane_num_waiting_vehicle_out"])

        # This will now return the best action index relative to the (potentially restricted) control_phases
        dic_feature["best_action_idx"] = self.get_max_pressure_phase_action(
            dic_feature["traffic_movement_pressure_queue"])

        dic_feature["traffic_movement_pressure_queue_efficient"] = self._get_traffic_movement_pressure_efficient(
            dic_feature["lane_num_waiting_vehicle_in"], dic_feature["lane_num_waiting_vehicle_out"])

        if not self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True):
            # AutoAgent controllers, rewards, canonical metrics, and graph-state
            # construction use only the basic phase/lane/pressure fields above.
            # CityLight/Attend/partial-observation features below traverse every
            # local vehicle every simulated second and are retained for RLLight.
            self.dic_feature = dic_feature
            return

        # Official CityLight state (for max_action_size=4):
        # [phase queue totals (4), phase lane sizes (4), phase count (1),
        #  previous action one-hot (4)]. Missing phases use queue=-1 and size=0.
        canonical_to_local, local_to_canonical, _ = self._four_phase_cache
        phase_queues = np.full(4, -1.0, dtype=np.float32)
        phase_sizes = np.zeros(4, dtype=np.float32)
        available_actions = np.zeros(4, dtype=np.float32)
        active_lane_indices = set()
        waiting_counts = dic_feature["lane_num_waiting_vehicle_in"]
        for canonical_index, lane_indices in enumerate(
            self._citylight_phase_lane_indices
        ):
            if canonical_index not in canonical_to_local:
                continue
            available_actions[canonical_index] = 1.0
            phase_sizes[canonical_index] = float(len(lane_indices))
            phase_queues[canonical_index] = float(
                sum(waiting_counts[index] for index in lane_indices)
            )
            active_lane_indices.update(lane_indices)

        previous_action = np.zeros(4, dtype=np.float32)
        local_action = self.phase_index_2_action_idx.get(
            self.current_green_phase_index, 0
        )
        canonical_action = local_to_canonical.get(local_action)
        if canonical_action is not None:
            previous_action[canonical_action] = 1.0
        dic_feature["citylight_observation"] = np.concatenate(
            (
                phase_queues,
                phase_sizes,
                np.asarray([available_actions.sum()], dtype=np.float32),
                previous_action,
            )
        ).tolist()
        dic_feature["citylight_available_actions"] = available_actions.tolist()
        # Generic per-intersection canonical-phase availability shared by every
        # masked controller: 1.0 when the phase exists in this intersection's
        # SUMO program (a phase that covers only one existing lane still counts
        # as available and just controls that lane), 0.0 otherwise.
        dic_feature["available_actions"] = available_actions.tolist()
        dic_feature["citylight_local_queue"] = float(
            sum(waiting_counts[index] for index in active_lane_indices)
        )
        dic_feature["citylight_neighbor_indices"] = list(
            self.citylight_graph_info["indices"]
        )
        dic_feature["citylight_neighbor_mask"] = list(
            self.citylight_graph_info["mask"]
        )
        dic_feature["citylight_neighbor_types"] = list(
            self.citylight_graph_info["types"]
        )
        dic_feature["citylight_neighbor_relations"] = np.asarray(
            self.citylight_graph_info["relations"], dtype=np.float32
        ).reshape(-1).tolist()
        dic_feature["citylight_neighbor_distances"] = np.asarray(
            self.citylight_graph_info["distances"], dtype=np.float32
        ).reshape(-1).tolist()

        dic_feature["traffic_movement_pressure_num"] = self._get_traffic_movement_pressure_general(
            dic_feature["lane_num_vehicle"], dic_feature["lane_num_vehicle_downstream"])

        # Both feature families segment the same local vehicles. Traverse them
        # once and reuse the results without changing either definition.
        partial_observations, attend_segments = self._collect_step_segment_features()
        tmp_part_n, tmp_part_q, tmp_efficient_part, enter_running_part, lepq = (
            self._get_part_traffic_movement_features(partial_observations)
        )
        dic_feature["lane_enter_running_part"] = list(enter_running_part)  # Ensure it's a list

        # Adjacency matrix row (placeholder, assumes fixed size/order from original code)
        # TODO: Adapt adjacency based on actual neighbors if needed by agent
        num_intersections = self.dic_traffic_env_conf.get("NUM_INTERSECTIONS", 1)  # Get total from config
        adj_row_len = min(self.dic_traffic_env_conf.get("TOP_K_ADJACENCY", 5), num_intersections)
        # Use placeholder if adjacency_info is not structured as expected
        dic_feature["adjacency_matrix"] = self.adjacency_info.get("adjacency_row", [0] * adj_row_len)[:adj_row_len]

        # Attend features (assume 12 lanes in/out)
        dic_feature["num_in_seg_attend"] = self._orgnize_several_segments_attend(
            dic_feature["lane_num_waiting_vehicle_in"],
            dic_feature["lane_num_waiting_vehicle_out"],
            attend_segments,
        )

        self.dic_feature = dic_feature
        # print(f"Debug {self.inter_id} features calculated: {list(dic_feature.keys())}")

    def _collect_step_segment_features(self):
        """Collect partial-observation and Attend segments in one traversal."""
        first_part_num_vehicle = defaultdict(list)
        last_part_num_vehicle = defaultdict(list)
        last_part_queue_vehicle = defaultdict(list)
        attend_part1 = defaultdict(list)
        attend_part2 = defaultdict(list)
        attend_part3 = defaultdict(list)

        partial_obs_length = self.dic_traffic_env_conf.get("OBS_LENGTH", 100)
        attend_obs_length = 100
        lane_lengths = self.dic_traffic_env_conf["lane_length"]

        for lane in self.list_entering_lanes + self.list_exiting_lanes:
            if lane is None:
                continue
            partial_lane_len = lane_lengths.get(lane, partial_obs_length)
            attend_lane_len = lane_lengths.get(lane, attend_obs_length * 3)
            if partial_lane_len <= 0 and attend_lane_len <= 0:
                continue

            last_part_boundary = max(
                0, partial_lane_len - partial_obs_length
            )
            for vehicle in self.dic_lane_vehicle_current_step.get(lane, []):
                if "shadow" in vehicle:
                    continue
                vehicle_distance = self.dic_vehicle_distance_current_step.get(
                    vehicle, 0
                )
                vehicle_speed = self.dic_vehicle_speed_current_step.get(vehicle, 0)

                if partial_lane_len > 0:
                    if vehicle_distance <= partial_obs_length:
                        first_part_num_vehicle[lane].append(vehicle)
                    if vehicle_distance >= last_part_boundary:
                        last_part_num_vehicle[lane].append(vehicle)
                        if vehicle_speed <= 0.1:
                            last_part_queue_vehicle[lane].append(vehicle)

                if attend_lane_len <= 0 or vehicle_speed <= 0.1:
                    continue
                if vehicle_distance > attend_lane_len - attend_obs_length:
                    attend_part1[lane].append(vehicle)
                elif (
                    attend_lane_len - 2 * attend_obs_length
                    < vehicle_distance
                    <= attend_lane_len - attend_obs_length
                ):
                    attend_part2[lane].append(vehicle)
                elif (
                    attend_lane_len - 3 * attend_obs_length
                    < vehicle_distance
                    <= attend_lane_len - 2 * attend_obs_length
                ):
                    attend_part3[lane].append(vehicle)

        return (
            (
                first_part_num_vehicle,
                last_part_num_vehicle,
                last_part_queue_vehicle,
            ),
            (attend_part1, attend_part2, attend_part3),
        )

    def _orgnize_several_segments_attend(
        self, queue_in, queue_out, attend_segments=None
    ):
        """ Prepares input for Attend model, assumes 12 lanes in/out. """
        if len(queue_in) != 12 or len(queue_out) != 12:
            print(
                f"Error ({self.inter_id}): _orgnize_several_segments_attend called with incorrect lane counts ({len(queue_in)}, {len(queue_out)}). Requires 12.")
            return [0] * (12 * 4 + 12 * 4)

        if attend_segments is None:
            attend_segments = self._get_several_segments_attend(
                lane_vehicles=self.dic_lane_vehicle_current_step,
                vehicle_distance=self.dic_vehicle_distance_current_step,
                vehicle_speed=self.dic_vehicle_speed_current_step,
                list_lanes=self.list_entering_lanes + self.list_exiting_lanes
            )
        part1, part2, part3 = attend_segments

        # Generate 12-element lists using the padded lane lists to ensure index safety
        run_in_part1 = [float(len(part1.get(lane, []))) if lane is not None else 0 for lane in self.list_entering_lanes]
        run_in_part2 = [float(len(part2.get(lane, []))) if lane is not None else 0 for lane in self.list_entering_lanes]
        run_in_part3 = [float(len(part3.get(lane, []))) if lane is not None else 0 for lane in self.list_entering_lanes]

        run_out_part1 = [float(len(part1.get(lane, []))) if lane is not None else 0 for lane in self.list_exiting_lanes]
        run_out_part2 = [float(len(part2.get(lane, []))) if lane is not None else 0 for lane in self.list_exiting_lanes]
        run_out_part3 = [float(len(part3.get(lane, []))) if lane is not None else 0 for lane in self.list_exiting_lanes]

        total_in, total_out = [], []
        for i in range(12):
            # Now these indices are safe since we're using the padded 12-element lists
            total_in.extend([run_in_part1[i], run_in_part2[i], run_in_part3[i], queue_in[i]])
            total_out.extend([run_out_part1[i], run_out_part2[i], run_out_part3[i], queue_out[i]])
        return total_in + total_out

    # ... (Rest of _get_several_segments_attend, _get_traffic_movement_pressure_efficient, etc.)

    def _get_several_segments_attend(self, lane_vehicles, vehicle_distance, vehicle_speed, list_lanes):
        """ Divides lanes into segments for Attend model features. """
        obs_length = 100
        part1, part2, part3 = defaultdict(list), defaultdict(list), defaultdict(list)
        for lane in list_lanes:
            if lane is None: continue

            # Use lane_length from CityFlowEnv's cache
            lane_len = self.dic_traffic_env_conf["lane_length"].get(lane, obs_length * 3)
            if lane_len <= 0: continue

            for vehicle in lane_vehicles.get(lane, []):
                if "shadow" in vehicle: continue
                v_speed = vehicle_speed.get(vehicle, 0)
                v_dist = vehicle_distance.get(vehicle, 0)

                if v_speed > 0.1:
                    if v_dist > lane_len - obs_length:
                        part1[lane].append(vehicle)
                    elif lane_len - 2 * obs_length < v_dist <= lane_len - obs_length:
                        part2[lane].append(vehicle)
                    elif lane_len - 3 * obs_length < v_dist <= lane_len - 2 * obs_length:
                        part3[lane].append(vehicle)
        return part1, part2, part3

    def _get_traffic_movement_pressure_efficient(self, enterings, exitings):
        """ Calculates pressure using downstream/3, assumes 12 lanes in WENSLR order. """
        if len(enterings) != 12 or len(exitings) != 12:
            return [0] * 12

        index_maps = {"W": [0, 1, 2], "E": [3, 4, 5], "N": [6, 7, 8], "S": [9, 10, 11]}
        turn_maps = ["S", "W", "N", "N", "E", "S", "W", "N", "E", "E", "S", "W"]

        outs_maps = {}
        for approach, indices in index_maps.items():
            outs_maps[approach] = sum(exitings[i] for i in indices) / 3.0

        t_m_p = [enterings[j] - outs_maps[turn_maps[j]] for j in range(12)]
        return t_m_p

    def _get_traffic_movement_pressure_general(self, enterings, exitings):
        """
        Calculates pressure based on dynamically determined road orientations and movements.
        Output is a fixed 12-element vector: W(L,T,R), E(L,T,R), N(L,T,R), S(L,T,R).
        """
        pressure_vector = []
        for entering_indices, exiting_indices in self._pressure_index_cache:
            entering_total = sum(
                enterings[idx] for idx in entering_indices if idx < len(enterings)
            )
            exiting_total = sum(
                exitings[idx] for idx in exiting_indices if idx < len(exitings)
            )
            pressure_vector.append(entering_total - exiting_total)
        return pressure_vector

    def _get_part_traffic_movement_features(self, partial_observations=None):
        """ Calculates features based on vehicles in specific segments of the lanes. Assumes 12 lanes. """
        if len(self.list_entering_lanes) != 12 or len(self.list_exiting_lanes) != 12:
            num_in = len(self.list_entering_lanes)
            return [0] * num_in, [0] * num_in, [0] * num_in, [0] * num_in, [0] * num_in

        if partial_observations is None:
            obs_length = self.dic_traffic_env_conf.get("OBS_LENGTH", 100)
            partial_observations = self._get_part_observations(
                lane_vehicles=self.dic_lane_vehicle_current_step,
                vehicle_distance=self.dic_vehicle_distance_current_step,
                vehicle_speed=self.dic_vehicle_speed_current_step,
                obs_length=obs_length,
                list_lanes=self.list_entering_lanes + self.list_exiting_lanes
            )
        f_p_num, l_p_num, l_p_q = partial_observations

        list_entering_part_queue = [len(l_p_q.get(lane, [])) if lane is not None else 0 for lane in
                                    self.list_entering_lanes]
        list_exiting_part_queue = [len(l_p_q.get(lane, [])) if lane is not None else 0 for lane in
                                   self.list_exiting_lanes]

        tmp_queue_efficient_part = self._get_traffic_movement_pressure_efficient(list_entering_part_queue,
                                                                                 list_exiting_part_queue)
        tmp_queue_part = self._get_traffic_movement_pressure_general(list_entering_part_queue, list_exiting_part_queue)

        list_entering_num_f = [len(f_p_num.get(lane, [])) if lane is not None else 0 for lane in
                               self.list_entering_lanes]
        list_entering_num_l = [len(l_p_num.get(lane, [])) if lane is not None else 0 for lane in
                               self.list_entering_lanes]
        entering_num = np.array(list_entering_num_f) + np.array(list_entering_num_l)

        list_exiting_num_f = [len(f_p_num.get(lane, [])) if lane is not None else 0 for lane in self.list_exiting_lanes]
        list_exiting_num_l = [len(l_p_num.get(lane, [])) if lane is not None else 0 for lane in self.list_exiting_lanes]
        exiting_num = np.array(list_exiting_num_f) + np.array(list_exiting_num_l)

        traffic_movement_pressure_nums = self._get_traffic_movement_pressure_general(entering_num.tolist(),
                                                                                     exiting_num.tolist())

        part_entering_running = np.array(list_entering_num_l) - np.array(list_entering_part_queue)

        return traffic_movement_pressure_nums, tmp_queue_part, tmp_queue_efficient_part, part_entering_running.tolist(), list_entering_part_queue

    def _get_part_observations(self, lane_vehicles, vehicle_distance, vehicle_speed, obs_length, list_lanes):
        """ Identifies vehicles in the first/last segments of lanes and waiting vehicles in the last segment. """
        first_part_num_vehicle = defaultdict(list)
        last_part_num_vehicle = defaultdict(list)
        last_part_queue_vehicle = defaultdict(list)

        for lane in list_lanes:
            if lane is None: continue

            # Now self is available since this is no longer a static method
            lane_len = self.dic_traffic_env_conf["lane_length"].get(lane, obs_length)

            if lane_len <= 0: continue

            last_part_obs_boundary = max(0, lane_len - obs_length)

            for vehicle in lane_vehicles.get(lane, []):
                if "shadow" in vehicle: continue

                v_dist = vehicle_distance.get(vehicle, 0)
                v_speed = vehicle_speed.get(vehicle, 0)

                if v_dist <= obs_length:
                    first_part_num_vehicle[lane].append(vehicle)

                if v_dist >= last_part_obs_boundary:
                    last_part_num_vehicle[lane].append(vehicle)
                    if v_speed <= 0.1:
                        last_part_queue_vehicle[lane].append(vehicle)

        return first_part_num_vehicle, last_part_num_vehicle, last_part_queue_vehicle

    def get_current_time(self):
        """Returns the current simulation time."""
        return self._current_sim_time

    def get_dic_vehicle_arrive_leave_time(self):
        """Returns the dictionary tracking vehicle arrival and departure times."""
        return self.dic_vehicle_arrive_leave_time

    def get_feature(self):
        """Returns the calculated dictionary of features for the current step."""
        return self.dic_feature

    def get_state(self, list_state_features):
        """
        Returns a dictionary containing the specified state features.
        """
        dic_state = {}
        for feature_name in list_state_features:
            dic_state[feature_name] = self.dic_feature.get(feature_name)
            if dic_state[feature_name] is None:
                print(f"Warning ({self.inter_id}): Requested state feature '{feature_name}' not found.")
                if "num" in feature_name or "pressure" in feature_name or "vehicle" in feature_name or "matrix" in feature_name or "attend" in feature_name:
                    dic_state[feature_name] = []
                elif "time" in feature_name:
                    dic_state[feature_name] = [0.0]
                elif "phase" in feature_name:
                    dic_state[feature_name] = [0]
                else:
                    dic_state[feature_name] = None
        return dic_state

    def get_reward(self, dic_reward_info):
        """
        Calculates the reward for the current step based on the configured metrics.
        """
        reward = 0.0
        if dic_reward_info.get("pressure", 0) != 0:
            pressure_val = np.sum(np.abs(self.dic_feature.get("pressure", [0])))
            reward += dic_reward_info["pressure"] * pressure_val

        if dic_reward_info.get("queue_length", 0) != 0:
            queue_val = np.sum(self.dic_feature.get("lane_num_waiting_vehicle_in", [0]))
            reward += dic_reward_info["queue_length"] * queue_val

        return reward

    def get_max_pressure_phase_action(self, pressures):
        """
        Calculates the action index corresponding to the traffic light phase
        that relieves the maximum pressure.
        """
        if not pressures or len(pressures) != 12:
            return 0

        if not self.control_phases:
            return 0

        max_pressure_sum = -float('inf')
        best_action_idx = 0

        for action_idx, phase_definition_str in enumerate(self.control_phases):
            current_phase_pressure_sum = 0.0
            movements_in_phase = []
            if len(phase_definition_str) % 2 == 0:
                for i in range(0, len(phase_definition_str), 2):
                    movements_in_phase.append(phase_definition_str[i:i + 2])
            else:
                continue

            for movement_code in movements_in_phase:
                pressure_idx = Intersection._MOVEMENT_TO_PRESSURE_IDX_MAP.get(movement_code)
                if pressure_idx is not None:
                    current_phase_pressure_sum += pressures[pressure_idx]

            if current_phase_pressure_sum > max_pressure_sum:
                max_pressure_sum = current_phase_pressure_sum
                best_action_idx = action_idx

        return best_action_idx


class SUMOEnv:
    """
    Generic SUMO Simulation Environment.

    Handles the overall simulation lifecycle, interacts with the SUMO engine via TraCI,
    manages multiple Intersection objects, and provides an API compatible with
    the original CityFlow-based environment.
    """

    def __init__(self, path_to_log, path_to_work_directory, dic_traffic_env_conf, dic_path, inter_phase_mapping=None):
        """
        Initializes the SUMO Environment.

        Args:
            path_to_log (str): Path to the logging directory.
            path_to_work_directory (str): Path to the working directory containing SUMO config files.
            dic_traffic_env_conf (dict): Environment configuration dictionary.
            dic_path (dict): Dictionary containing paths to data files.
            inter_phase_mapping (dict, optional): Dictionary mapping intersection_id to a list
                                   of allowed phase name strings.
        """
        self.path_to_log = path_to_log
        self.path_to_work_directory = path_to_work_directory
        self.dic_traffic_env_conf = dic_traffic_env_conf
        self.dic_path = dic_path
        self.inter_phase_mapping = inter_phase_mapping if inter_phase_mapping is not None else {}

        # --- SUMO Process and TraCI Connection Management ---
        self.sumo_process = None
        self.traci_conn = None
        self._simulation_running = False
        self.sumo_stdout_log = os.path.join(self.path_to_log, "sumo_stdout.log")
        self.sumo_stderr_log = os.path.join(self.path_to_log, "sumo_stderr.log")
        self.sumo_net = None  # Cache for the parsed sumolib network object
        # --- End of SUMO Management ---

        self.roadnet = None # Kept for compatibility, but self.sumo_net is the primary source
        self.roads_data = {}  # Legacy format: road_id -> road_json
        self.intersections_data = {}  # Legacy format: tls_id -> inter_json

        self.list_intersection = []  # List of Intersection objects
        self.intersection_dict = {}  # Compatibility: inter_id -> parsed info dict
        self.id_to_index = {}  # Maps intersection id to index in list_intersection
        self._inter_by_id = {}  # inter_id -> Intersection object (rebuilt in reset)
        self.list_inter_log = []

        self.list_lanes = []  # List of all unique lane IDs in the network
        self.lane_length = {}  # lane_id -> length

        self.system_states = {}  # Stores results from bulk TraCI API calls
        self.current_time = 0.0
        self.waiting_vehicle_list = {}
        self._seen_vehicle_ids = set()
        self._total_waiting_time_by_vehicle = {}
        self._intersection_queue_sum = 0.0
        self._intersection_queue_count = 0
        self._queue_observation_steps = 0
        # --- Travel-time aggregator (fallback for SUMO versions without getArrivedMeanTravelTime) ---
        self._depart_time_by_vehicle = {}   # vid -> depart_time
        self._arrived_tt_sum = 0.0          # sum of travel times of arrived vehicles
        self._arrived_count = 0             # count of arrived vehicles
        self._arrived_vehicle_tt = {}       # optional: vid -> travel time (for debugging/analysis)
        self._subscribed_vehicle_ids = set()
        self._vehicle_tracking_initialized = False
        self._vehicle_subscription_reconcile_needed = False
        self._trafficlight_phase_subscription_enabled = False
        self._sim_subscription_active = False
        self._sim_subscription_ready = False
        self._last_min_expected = None
        # Observers used by the shared rolling evaluator.  They are intentionally
        # retained across reset/load operations unless explicitly removed.
        self._step_listeners = []
        self._canonical_reward_sum = 0.0

        self._default_port = self._resolve_traci_port()
        # Per-instance counter incremented on every reset() so each SUMO launch
        # in an episode gets a fresh TraCI port. This avoids reusing a port that
        # is still in TIME_WAIT after close() (SUMO's TraCI socket does not set
        # SO_REUSEADDR -> "Address already in use") and, with the bind probe in
        # _next_traci_port, avoids ports held by concurrent workers.
        self._port_offset = 0
        # --- Configuration Validation ---
        min_action_time = self.dic_traffic_env_conf.get("MIN_ACTION_TIME", 15)
        green_time = self.dic_traffic_env_conf.get(
            "GREEN_TIME",
            min_action_time - DEFAULT_YELLOW_TIME,
        )
        yellow_time = self.dic_traffic_env_conf.get(
            "YELLOW_TIME",
            DEFAULT_YELLOW_TIME,
        )
        if green_time <= 0:
            print("Warning: GREEN_TIME should be positive.")
        if yellow_time <= 0:
            print("Warning: YELLOW_TIME should be positive.")
        if min_action_time <= 0:
            print("Warning: MIN_ACTION_TIME should be positive.")
        if green_time + yellow_time != min_action_time:
            print(
                "Warning: GREEN_TIME + YELLOW_TIME should equal "
                "MIN_ACTION_TIME for synchronous adaptive control."
            )

        # --- Ensure Log Directory Exists ---
        os.makedirs(self.path_to_log, exist_ok=True)

        print("SUMO Environment initialized. Call reset() to start simulation.")

    def _resolve_traci_port(self):
        """Return an explicit TraCI port when a parallel rollout worker provides one."""
        candidates = (
            self.dic_traffic_env_conf.get("SUMO_PORT"),
            self.dic_traffic_env_conf.get("TRACI_PORT"),
            os.environ.get("EVOLVELIGHT_SUMO_PORT"),
        )
        for value in candidates:
            if value in (None, ""):
                continue
            try:
                port = int(value)
            except (TypeError, ValueError):
                continue
            if port > 0:
                return port
        pid_offset = os.getpid() % 20000
        return 8813 + pid_offset

    @staticmethod
    def _port_is_free(port: int) -> bool:
        """True if a SUMO TraCI server can bind to ``port`` right now.

        SUMO's TraCI listening socket does not set SO_REUSEADDR, so a port in
        TIME_WAIT (recently closed) or held by another process is unusable and
        SUMO exits with "Address already in use". We probe WITHOUT SO_REUSEADDR
        so such ports are correctly reported as busy.
        """
        import socket as _socket
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        try:
            try:
                sock.bind(("", port))
            except OSError:
                return False
        finally:
            sock.close()
        return True

    def _next_traci_port(self, max_tries: int = 200) -> int:
        """Allocate a free TraCI port, skipping in-use/TIME_WAIT ports.

        Increments a per-instance offset so each ``reset()`` in an episode uses
        a distinct port (no within-episode TIME_WAIT reuse), and the bind probe
        skips ports held by concurrent workers so cross-episode launches don't
        collide either.
        """
        base = self._default_port
        offset = self._port_offset
        for i in range(max_tries):
            port = base + offset + i
            if 0 < port < 65536 and self._port_is_free(port):
                self._port_offset = offset + i + 1
                return port
        # Fallback: return the next offset even if the probe said busy (rare;
        # the launch retry loop in reset() will still handle a collision).
        port = base + offset
        self._port_offset = offset + 1
        return port

    def _load_roadnet(self):
        """
        Loads and parses the SUMO network file (.net.xml) using sumolib.
        Translates the SUMO network topology into the legacy dictionary formats
        and caches the results. This acts as the Anti-Corruption Layer for static data.
        """
        net_file_name = self.dic_traffic_env_conf.get("ROADNET_FILE", "map.net.xml")
        net_file_path = os.path.join(self.dic_path.get("PATH_TO_DATA", self.path_to_work_directory), net_file_name)

        if not os.path.exists(net_file_path):
            raise FileNotFoundError(f"SUMO network file '{net_file_path}' not found.")

        print(f"Loading SUMO network from: {net_file_path}")
        try:
            # 1. One-Time Parsing and Caching of the sumolib object
            self.sumo_net = sumolib.net.readNet(net_file_path)
        except Exception as e:
            # Catches XML parsing errors and other sumolib issues
            raise ValueError(f"Failed to parse SUMO network file '{net_file_path}': {e}")

        # 2. Translate SUMO topology into legacy formats
        # --- Translate Intersections (Traffic Light Systems) ---
        self.intersections_data = {}
        
        # NEW: TLS↔node mappings for robust planning
        self.tls_to_nodes = {}   # TLS id -> [node ids]
        self.node_to_tls = {}    # node id -> TLS id
        
        for tls in self.sumo_net.getTrafficLights():
            tls_id = tls.getID()

            # Nodes controlled by this TLS (empty for some nets / versions)
            nodes = getattr(tls, "getNodes", lambda: [])()
            node_ids = [n.getID() for n in nodes] if nodes else []

            # Coordinates (your existing code)
            nodes_for_xy = nodes
            if nodes_for_xy:
                xs, ys = zip(*(n.getCoord() for n in nodes_for_xy))
                x, y = sum(xs) / len(xs), sum(ys) / len(ys)
            else:
                try:
                    node = self.sumo_net.getNode(tls_id)
                    x, y = node.getCoord()
                except Exception:
                    x, y = 0.0, 0.0

            # Save mapping + some useful metadata
            self.tls_to_nodes[tls_id] = node_ids
            for nid in node_ids:
                self.node_to_tls[nid] = tls_id

            self.intersections_data[tls_id] = {
                "id": tls_id,
                "virtual": False,
                "point": {"x": x, "y": y},
                "controlled_nodes": node_ids,         # NEW
                "graph_node_ids": node_ids or [tls_id]# NEW: how planners can address this TLS in graphs
            }

        # --- Translate Roads (Edges) ---
        self.roads_data = {}
        for edge in self.sumo_net.getEdges():
            edge_id = edge.getID()
            if edge_id.startswith(":"): # Ignore internal edges
                continue
            
            points = [{"x": x, "y": y} for x, y in edge.getShape()]
            lanes_info = [{"maxSpeed": lane.getSpeed()} for lane in edge.getLanes()]

            self.roads_data[edge_id] = {
                "id": edge_id,
                "lanes": lanes_info,
                "startIntersection": edge.getFromNode().getID(),
                "endIntersection": edge.getToNode().getID(),
                "points": points,
            }

        self.dic_traffic_env_conf["NUM_INTERSECTIONS"] = len(self.intersections_data)
        print(f"Found {len(self.roads_data)} roads (edges) and {len(self.intersections_data)} signalized intersections (TLS).")

    def get_lane_speed(self, lane_id):
        """Returns the speed limit of the specified lane."""
        return self.sumo_net.getLane(lane_id).getSpeed()

    def _get_lane_length(self):
        """Calculates and caches the length of each lane from the parsed sumolib network."""
        self.lane_length = {}
        if not self.sumo_net:
            print("Warning: Cannot calculate lane lengths, SUMO network not loaded.")
            return

        for edge in self.sumo_net.getEdges():
            # Include all lanes, even internal junction lanes
            for lane in edge.getLanes():
                self.lane_length[lane.getID()] = lane.getLength()

        print(f"Cached lengths for {len(self.lane_length)} lanes.")

    def _adjacency_extraction(self):
        """
        Extracts adjacency information based on geometric proximity.
        """
        if not self.intersections_data:
            return {}

        adjacency_results = {}
        inter_ids = list(self.intersections_data.keys())
        inter_id_to_idx_map = {inter_id: i for i, inter_id in enumerate(inter_ids)}
        num_intersections = len(inter_ids)
        top_k = min(self.dic_traffic_env_conf.get("TOP_K_ADJACENCY", 5), num_intersections)

        print(f"Calculating adjacency for {num_intersections} intersections (top_k={top_k})...")

        for i, inter_id in enumerate(inter_ids):
            loc_i = self.intersections_data[inter_id]["point"]
            distances = np.full(num_intersections, np.inf)

            for j, other_inter_id in enumerate(inter_ids):
                if i == j:
                    distances[j] = 0
                    continue
                loc_j = self.intersections_data[other_inter_id]["point"]
                distances[j] = self._cal_distance(loc_i, loc_j)
            
            if num_intersections <= top_k:
                neighbor_indices = [idx for idx in range(num_intersections) if idx != i]
                neighbor_distances = distances[neighbor_indices]
                sorted_neighbor_indices = np.array(neighbor_indices)[np.argsort(neighbor_distances)]
                adjacency_row = [i] + sorted_neighbor_indices.tolist()
            else:
                partitioned_indices = np.argpartition(distances, top_k)
                candidate_indices = partitioned_indices[:top_k + 1]
                candidate_distances = distances[candidate_indices]
                sorted_candidate_indices_local = np.argsort(candidate_distances)
                sorted_candidate_indices_global = candidate_indices[sorted_candidate_indices_local]
                neighbor_indices = [idx for idx in sorted_candidate_indices_global if idx != i][:top_k]
                adjacency_row = [i] + neighbor_indices

            adjacency_results[inter_id] = {
                "adjacency_row": adjacency_row,
                "total_inter_num": num_intersections,
                "inter_id_to_index": inter_id_to_idx_map,
            }

        return adjacency_results

    def _build_citylight_graph(self):
        """Build CityLight's directed four-slot relative-neighbour metadata."""
        for destination_index, destination in enumerate(self.list_intersection):
            candidates = []
            destination_in_roads = set(destination.incoming_roads)
            destination_in_lanes = {
                lane
                for phase in destination._citylight_phase_lanes
                for lane in phase[0]
            }
            for source_index, source in enumerate(self.list_intersection):
                if source_index == destination_index:
                    continue
                shared_roads = set(source.outgoing_roads) & destination_in_roads
                if not shared_roads:
                    continue

                relation = np.zeros(2, dtype=np.float32)
                neighbour_type = 0
                source_phases = [
                    phase
                    for phase_index, phase in enumerate(source._citylight_phase_lanes)
                    if phase_index in source._four_phase_cache[0]
                ]
                destination_phases = [
                    phase
                    for phase_index, phase in enumerate(
                        destination._citylight_phase_lanes
                    )
                    if phase_index in destination._four_phase_cache[0]
                ]
                source_out_lanes = {
                    lane for phase in source_phases for lane in phase[1]
                }
                for destination_phase_index, destination_phase in enumerate(
                    destination_phases
                ):
                    if not (set(destination_phase[0]) & source_out_lanes):
                        continue
                    if len(source_phases) > 2:
                        if (
                            set(source_phases[2][1]) & destination_in_lanes
                            or set(source_phases[1][1]) & destination_in_lanes
                        ):
                            relation[:] = (1.0, 0.0)
                        else:
                            relation[:] = (0.0, 1.0)
                    elif len(source_phases) == 2:
                        if set(source_phases[1][1]) & destination_in_lanes:
                            relation[:] = (1.0, 0.0)
                        else:
                            relation[:] = (0.0, 1.0)
                    neighbour_type = 0 if destination_phase_index in (0, 1) else 1

                road_lengths = []
                strength = 0
                for road_id in shared_roads:
                    try:
                        road = self.sumo_net.getEdge(road_id)
                        lanes = road.getLanes()
                        strength += len(lanes)
                        road_lengths.extend(lane.getLength() for lane in lanes)
                    except (KeyError, AttributeError):
                        continue
                distance = min(min(road_lengths) if road_lengths else 0.0, 500.0) / 100.0
                candidates.append(
                    {
                        "index": source_index,
                        "type": neighbour_type,
                        "relation": relation.tolist(),
                        "distance": [distance, float(strength)],
                    }
                )

            # The official implementation reserves slots 0-1 for type A and
            # slots 2-3 for type B.
            graph_info = {
                "indices": [0, 0, 0, 0],
                "mask": [0.0, 0.0, 0.0, 0.0],
                "types": [0.0, 0.0, 0.0, 0.0],
                "relations": [[0.0, 0.0] for _ in range(4)],
                "distances": [[0.0, 0.0] for _ in range(4)],
            }
            for neighbour_type, slot_start in ((0, 0), (1, 2)):
                same_type = [
                    item for item in candidates if item["type"] == neighbour_type
                ][:2]
                for offset, item in enumerate(same_type):
                    slot = slot_start + offset
                    graph_info["indices"][slot] = item["index"]
                    graph_info["mask"][slot] = 1.0
                    graph_info["types"][slot] = float(neighbour_type)
                    graph_info["relations"][slot] = item["relation"]
                    graph_info["distances"][slot] = item["distance"]
            destination.citylight_graph_info = graph_info

    @staticmethod
    def _cal_distance(loc_dict1, loc_dict2):
        """Calculates Euclidean distance between two points."""
        x1, y1 = loc_dict1.get('x', 0), loc_dict1.get('y', 0)
        x2, y2 = loc_dict2.get('x', 0), loc_dict2.get('y', 0)
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    @_seg_wrap("sumo_init")  # [SEG-TIMING] SUMO launch + connect + subscribe
    def reset(self, use_gui=False, seed=None, load_state_path=None):
        """
        Resets the simulation environment.
        - Shuts down any existing SUMO simulation.
        - Dynamically creates the .sumocfg file in the work directory.
        - Launches a new SUMO instance (with or without GUI).
        - Establishes a TraCI connection.
        - Initializes Intersection objects.
        - Retrieves initial state.
        
        Args:
            use_gui (bool): Whether to use sumo-gui.
            seed (int, optional): Random seed for the simulation.
            load_state_path (str, optional): If provided, starts the simulation from this snapshot file.
        """
        print("================ Starting Environment Reset ================")
        self.close()

        self.current_time = 0.0
        self.waiting_vehicle_list = {}
        self._seen_vehicle_ids = set()
        self._total_waiting_time_by_vehicle = {}
        self._intersection_queue_sum = 0.0
        self._intersection_queue_count = 0
        self._queue_observation_steps = 0
        # Reset travel-time aggregate
        self._depart_time_by_vehicle = {}
        self._arrived_tt_sum = 0.0
        self._arrived_count = 0
        self._arrived_vehicle_tt = {}
        self._subscribed_vehicle_ids = set()
        self._vehicle_tracking_initialized = False
        self._vehicle_subscription_reconcile_needed = False
        self._trafficlight_phase_subscription_enabled = False
        self._sim_subscription_active = False
        self._sim_subscription_ready = False
        self._last_min_expected = None
        self._canonical_reward_sum = 0.0

        # 1. Load static network data once
        if self.sumo_net is None:
            self._load_roadnet()
            self._get_lane_length()

        # 2. Prepare SUMO configuration files in the work directory
        data_path = self.dic_path.get("PATH_TO_DATA", self.path_to_work_directory)

        # Get source file names and paths
        net_file_name = self.dic_traffic_env_conf.get("ROADNET_FILE", "map.net.xml")
        flow_file_name = self.dic_traffic_env_conf.get("TRAFFIC_FILE", "route.rou.xml")
        
        source_net_path = os.path.join(data_path, net_file_name)
        source_flow_path = os.path.join(data_path, flow_file_name)

        if not os.path.exists(source_net_path):
            raise FileNotFoundError(f"SUMO network file not found at source: {source_net_path}")
        if not os.path.exists(source_flow_path):
            raise FileNotFoundError(f"SUMO route file not found at source: {source_flow_path}")

        # Defensive: the per-rollout work dir (sumo_<traffic> / sumo_test_<traffic>)
        # can be transiently missing (same race that left memories.txt unwritable) --
        # a gone dir makes the shutil.copy below raise FileNotFoundError on the dest
        # path, which sabotaged TRAIN_AND_SIMULATION's "test with secondary simulator".
        # Recreate it before copying the SUMO files in.
        os.makedirs(self.path_to_work_directory, exist_ok=True)

        # Define destination paths in the work directory
        dest_net_path = os.path.join(self.path_to_work_directory, net_file_name)
        dest_flow_path = os.path.join(self.path_to_work_directory, flow_file_name)

        # Copy files to the work directory
        shutil.copy(source_net_path, dest_net_path)
        shutil.copy(source_flow_path, dest_flow_path)
        
        # Generate and write the sumocfg file
        sumocfg_file_name = self.dic_traffic_env_conf.get("SUMOCFG_FILE", "map.sumocfg")
        sumocfg_path = os.path.join(self.path_to_work_directory, sumocfg_file_name)

        sumocfg_content = f"""<configuration>
    <input>
        <net-file value="{net_file_name}"/>
        <route-files value="{flow_file_name}"/>
    </input>
</configuration>
"""
        with open(sumocfg_path, 'w') as f:
            f.write(sumocfg_content)
        
        # 3. Prepare and Launch SUMO
        sumo_binary = "sumo"
        
        if seed is None:
            configured_seed = self.dic_traffic_env_conf.get("SEED")
            seed = (
                int(configured_seed)
                if configured_seed is not None
                else int(np.random.randint(0, 10000))
            )

        # 设置仿真时间
        sim_time = self.dic_traffic_env_conf.get("RUN_COUNTS", 3600)
        # Base SUMO command; the port is appended per attempt below so each
        # retry can use a fresh port if the previous one collided.
        sumo_cmd_base = [
            sumo_binary, "-c", sumocfg_path,
            "--seed", str(seed),
            "--step-length", str(self.dic_traffic_env_conf.get("INTERVAL", 1.0)),
            "--no-warnings", "true",
            # "--end", str(sim_time)
        ]

        # Add --begin to start from a specific time (e.g., 28800 for 8 AM).
        # A loaded state already embeds its own (later) simulation time, so
        # --begin is redundant/conflicting there; _start_time then only feeds
        # the absolute end-time bookkeeping in get_state().
        if (
            hasattr(self, '_start_time')
            and self._start_time > 0
            and not load_state_path
        ):
            sumo_cmd_base.extend(["--begin", str(self._start_time)])
            print(f"Setting SUMO start time to {self._start_time}s")

        # MODIFICATION: Add the --load-state argument if a path is provided
        if load_state_path and os.path.exists(load_state_path):
            print(f"Attempting to load simulation from state: {load_state_path}")
            sumo_cmd_base.extend(["--load-state", load_state_path])
        elif load_state_path:
            print(f"Warning: Snapshot file for loading not found at {load_state_path}. Starting new simulation.")

        sumo_stdout_log = self.sumo_stdout_log
        sumo_stderr_log = self.sumo_stderr_log

        # Launch SUMO, retrying with a fresh port on "Address already in use"
        # (TIME_WAIT from a previous reset() in this episode, or a port held by
        # a concurrent worker). Each attempt uses _next_traci_port(), which both
        # increments a per-instance offset and bind-probes for a free port.
        max_port_retries = 50
        launched = False
        for _port_attempt in range(max_port_retries):
            self._traci_port = self._next_traci_port()
            sumo_cmd = sumo_cmd_base + ["--remote-port", str(self._traci_port)]
            print(f"Launching SUMO with command: {' '.join(sumo_cmd)}")
            try:
                with open(sumo_stdout_log, 'w') as f_out, open(sumo_stderr_log, 'w') as f_err:
                    self.sumo_process = subprocess.Popen(sumo_cmd, stdout=f_out, stderr=f_err)
            except Exception:
                self.sumo_process = None
                continue

            # Give SUMO a moment to start up or crash
            time.sleep(5)

            # SUMO still running -> success.
            if self.sumo_process.poll() is None:
                launched = True
                break

            # SUMO exited; read stderr to decide whether to retry on port collision.
            try:
                with open(sumo_stderr_log, 'r') as f_err_read:
                    error_details = f_err_read.read()
            except IOError:
                error_details = ""
            self.close()
            if "Address already in use" in error_details and _port_attempt < max_port_retries - 1:
                print(f"Warning: SUMO port {self._traci_port} already in use; retrying with a new port...")
                continue
            # Non-port error (or retries exhausted): surface the real error.
            error_message = f"SUMO process terminated unexpectedly. Check SUMO logs for details:\n"
            error_message += f"  - STDERR: {sumo_stderr_log}\n"
            if error_details.strip():
                error_message += f"\n--- SUMO Error Log Content ---\n{error_details}\n----------------------------"
            else:
                error_message += "(No error details in stderr / could not read error log file.)"
            raise RuntimeError(error_message)

        if not launched:
            raise RuntimeError(
                f"SUMO failed to start after {max_port_retries} port attempts. "
                f"Last STDERR log: {sumo_stderr_log}"
            )

        # 4. Establish TraCI Connection
        try:
            self.traci_conn = traci.connect(port=self._traci_port, numRetries=10)

            # Lane subscriptions happen after the intersections are built
            # below: the light path subscribes only controller-adjacent lanes,
            # which requires the parsed intersection topology.
            self._subscribe_trafficlight_phases()
            self._subscribe_simulation_domain()

            self._simulation_running = True
            print(f"Successfully connected to SUMO (seed: {seed}).")

        except FileNotFoundError:
            raise EnvironmentError(f"'{sumo_binary}' not found. Please ensure SUMO is installed and in your system's PATH.")
        except traci.TraCIException as e:
            error_message = (f"Failed to connect to SUMO via TraCI. This often means SUMO crashed on startup. "
                             f"Please check the SUMO log files for errors:\n"
                             f"  - STDERR: {sumo_stderr_log}\n"
                             f"Original TraCI error: {e}")
            try:
                with open(sumo_stderr_log, 'r') as f_err_read:
                     error_details = f_err_read.read()
                     if error_details.strip():
                         error_message += f"\n\n--- SUMO Error Log Content ---\n{error_details}\n----------------------------"
            except IOError:
                pass
            self.close()
            raise EnvironmentError(error_message) from e
        except Exception as e:
            self.close()
            raise

        # 5. Calculate Adjacency
        self.adjacency_map = self._adjacency_extraction()

        # 6. Initialize Intersection Objects
        self.list_intersection = []
        self.id_to_index = {}
        self.list_inter_log = []
        print(f"Creating Intersection objects for {len(self.intersections_data)} intersections...")
        
        # Pass the global lane_length dict to the intersection for use in feature calcs
        self.dic_traffic_env_conf["lane_length"] = self.lane_length
        
        for idx, (inter_id, _) in enumerate(self.intersections_data.items()):
            adjacency_info = self.adjacency_map.get(inter_id, {})
            custom_phases = self.inter_phase_mapping.get(inter_id)
            try:
                intersection = Intersection(
                    tls_id=inter_id,
                    dic_traffic_env_conf=self.dic_traffic_env_conf,
                    traci_conn=self.traci_conn,
                    sumo_net=self.sumo_net,
                    path_to_log=self.path_to_log,
                    adjacency_info=adjacency_info,
                    custom_phase_list=custom_phases
                )
                self.list_intersection.append(intersection)
                self.id_to_index[inter_id] = idx
                self.list_inter_log.append([])
            except Exception as e:
                print(f"ERROR: Failed to initialize Intersection object for {inter_id}: {e}")
                self.close()
                raise

        # id -> Intersection object map for per-decision graph-state builders;
        # rebuilt on every reset because reset constructs fresh objects.
        self._inter_by_id = {
            inter.inter_id: inter for inter in self.list_intersection
        }

        # Subscribe to lane-based information once. The light path reads only
        # lanes adjacent to a signalized intersection (features, graph lane
        # groups, and strict-pressure downstream lookups all resolve to
        # incoming/outgoing road lanes), so mid-block lanes are skipped;
        # detailed logging keeps the full-network set its legacy consumers
        # may read.
        if self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True):
            subscription_lane_ids = self.lane_length.keys()
        else:
            subscription_lane_ids = self._controller_lane_ids()
        for lane_id in subscription_lane_ids:
            self.traci_conn.lane.subscribe(lane_id, [
                traci.constants.LAST_STEP_VEHICLE_HALTING_NUMBER,
                traci.constants.LAST_STEP_VEHICLE_ID_LIST
            ])

        self._build_citylight_graph()

        # 7. Get Initial State from Simulator
        # MODIFICATION: If loading from state, the first step is not needed as SUMO is already at that time.
        # Otherwise, take one step to populate the network with initial vehicles.
        print("Getting initial simulator state...")
        performed_initial_step = not load_state_path
        if not load_state_path:
            self.traci_conn.simulationStep()
        self._update_system_states()

        # 8. Update Intersection Measurements
        print("Updating initial intersection measurements...")
        for inter in self.list_intersection:
            inter.update_current_measurements(self.system_states)

        # The population step above is a real simulated second. Include it in
        # canonical counters so a logical 0-12h run contains exactly 43,200
        # seconds of queue/wait/reward observations. Loaded snapshots do not
        # advance SUMO and therefore must not be accumulated here.
        if performed_initial_step:
            self._update_waiting_vehicles()
            self._accumulate_intersection_queue_metrics()

        # 9. Create intersection_dict (for compatibility)
        print("Creating compatibility intersection_dict...")
        self.create_intersection_dict()

        # 10. Get Formatted Initial State
        state, _ = self.get_state()

        print("================ Environment Reset Complete ================")
        return state

    def _controller_lane_ids(self):
        """Lanes of every road adjacent to a signalized intersection.

        Strict superset of the light path's lane reads: the padded
        entering/exiting feature lists (which cap at three lanes per
        orientation), the lane_inter_graph lane groups, and the
        strict-pressure downstream lanes all resolve to incoming/outgoing
        road lanes.
        """
        lane_ids = set()
        for inter in self.list_intersection:
            for roads in (inter.incoming_roads, inter.outgoing_roads):
                for road_obj in roads.values():
                    for lane_obj in road_obj.getLanes():
                        lane_ids.add(lane_obj.getID())
        return lane_ids

    def _subscribe_trafficlight_phases(self):
        """Subscribe once to current phases so all junctions share one batch read."""
        phase_variable = getattr(traci.constants, "TL_CURRENT_PHASE", None)
        if phase_variable is None:
            self._trafficlight_phase_subscription_enabled = False
            return

        try:
            for tls_id in self.intersections_data:
                self.traci_conn.trafficlight.subscribe(tls_id, [phase_variable])
            self._trafficlight_phase_subscription_enabled = True
        except (traci.TraCIException, AttributeError):
            self._trafficlight_phase_subscription_enabled = False

    def _subscribe_simulation_domain(self):
        """Subscribe lifecycle/time vars so they ride the simulationStep response.

        departed/arrived ID lists, current time, and min-expected-vehicles
        otherwise cost four synchronous RPCs per simulated second. The
        subscription values are only trustworthy after a simulationStep has
        flushed them: callers gate on ``_sim_subscription_ready`` (flipped in
        ``step`` after the first post-step state update) and fall back to
        direct queries until then.
        """
        self._sim_subscription_active = False
        self._sim_subscription_ready = False
        try:
            # The simulation domain's subscribe takes the variable list as its
            # first argument; the subscribed object id is fixed to "".
            self.traci_conn.simulation.subscribe([
                traci.constants.VAR_DEPARTED_VEHICLES_IDS,
                traci.constants.VAR_ARRIVED_VEHICLES_IDS,
                traci.constants.VAR_TIME,
                traci.constants.VAR_MIN_EXPECTED_VEHICLES,
            ])
            self._sim_subscription_active = True
        except (traci.TraCIException, AttributeError) as e:
            print(
                f"Warning: simulation-domain subscription unavailable "
                f"({e}); keeping direct per-second queries."
            )

    def _read_sim_domain_vars(self):
        """Read lifecycle/time vars from the simulation-domain subscription.

        Returns ``(departed_ids, arrived_ids, now_time, min_expected)`` or
        ``None`` when the subscription is unusable (not subscribed, not yet
        flushed by a step, or empty results) so callers fall back to direct
        queries. ``min_expected`` may be ``None`` inside a valid result when
        the variable itself was not delivered.
        """
        if not (self._sim_subscription_active and self._sim_subscription_ready):
            return None
        try:
            # traci >= 1.x exposes the "" object's results directly; older
            # layouts only offer the {object_id: results} map.
            try:
                data = self.traci_conn.simulation.getSubscriptionResults()
            except AttributeError:
                data = (
                    self.traci_conn.simulation.getAllSubscriptionResults() or {}
                ).get("", {})
        except (traci.TraCIException, AttributeError):
            return None
        if not isinstance(data, dict) or not data:
            return None
        departed = data.get(traci.constants.VAR_DEPARTED_VEHICLES_IDS)
        arrived = data.get(traci.constants.VAR_ARRIVED_VEHICLES_IDS)
        now_time = data.get(traci.constants.VAR_TIME)
        if departed is None or arrived is None or now_time is None:
            return None
        min_expected = data.get(traci.constants.VAR_MIN_EXPECTED_VEHICLES)
        return (
            departed,
            arrived,
            float(now_time),
            None if min_expected is None else int(min_expected),
        )

    def _subscribe_vehicles(self, vehicle_ids):
        """Subscribe newly active vehicles and return those successfully added."""
        subscribed_now = []
        if self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True):
            variables = [
                traci.constants.VAR_SPEED,
                traci.constants.VAR_LANE_ID,
                traci.constants.VAR_LANEPOSITION,
            ]
        else:
            # Light path: per-second consumers only need speed (waiting-time
            # accumulation). Lane membership comes from the lane
            # subscriptions; positions are fetched on demand by
            # refresh_vehicle_positions() for the final traffic snapshot.
            variables = [traci.constants.VAR_SPEED]
        for vehicle_id in vehicle_ids:
            if vehicle_id in self._subscribed_vehicle_ids:
                continue
            try:
                self.traci_conn.vehicle.subscribe(vehicle_id, variables)
            except traci.TraCIException:
                self._vehicle_subscription_reconcile_needed = True
                continue
            self._subscribed_vehicle_ids.add(vehicle_id)
            subscribed_now.append(vehicle_id)
        return subscribed_now

    def _read_log_tail(self, path, max_chars=4000):
        if not path or not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as log_file:
                content = log_file.read()
        except OSError:
            return ""
        return content[-max_chars:]

    def _sumo_log_summary(self):
        details = []
        for label, path in (
            ("STDERR", self.sumo_stderr_log),
            ("STDOUT", self.sumo_stdout_log),
        ):
            tail = self._read_log_tail(path)
            if tail.strip():
                details.append(f"\n--- SUMO {label} tail: {path} ---\n{tail}")
        return "".join(details)

    def _update_system_states(self, full_feature_update=True):
        """
        Subscribe new vehicles and retrieve the current state in batched calls.
        """
        if not self._simulation_running:
            return

        try:
            # Query lifecycle events once. After initial reconciliation, only
            # newly departed vehicles need subscription commands. Prefer the
            # simulation-domain subscription (values arrived with the last
            # simulationStep response); direct queries cover the pre-flush
            # boundary after reset/load and any subscription failure.
            lifecycle_query_failed = False
            sim_vars = self._read_sim_domain_vars()
            self._last_min_expected = sim_vars[3] if sim_vars is not None else None
            try:
                if sim_vars is not None:
                    departed_ids = list(sim_vars[0])
                    arrived_ids = list(sim_vars[1])
                else:
                    departed_ids = list(self.traci_conn.simulation.getDepartedIDList())
                    arrived_ids = list(self.traci_conn.simulation.getArrivedIDList())
            except traci.TraCIException:
                departed_ids, arrived_ids = [], []
                lifecycle_query_failed = True

            reconciled_active_vehicles = (
                not self._vehicle_tracking_initialized
                or self._vehicle_subscription_reconcile_needed
                or lifecycle_query_failed
            )
            if reconciled_active_vehicles:
                subscription_candidates = list(self.traci_conn.vehicle.getIDList())
                active_vehicle_set = set(subscription_candidates)
                self._subscribed_vehicle_ids.intersection_update(active_vehicle_set)
                self._vehicle_subscription_reconcile_needed = False
            else:
                subscription_candidates = departed_ids
            self._subscribe_vehicles(subscription_candidates)

            # Batch retrieval for all active subscriptions.
            vehicle_results = (
                self.traci_conn.vehicle.getAllSubscriptionResults() or {}
            )
            lane_results = self.traci_conn.lane.getAllSubscriptionResults() or {}
            trafficlight_results = {}
            if self._trafficlight_phase_subscription_enabled:
                try:
                    trafficlight_results = (
                        self.traci_conn.trafficlight.getAllSubscriptionResults()
                    )
                except (traci.TraCIException, AttributeError):
                    self._trafficlight_phase_subscription_enabled = False

            self.system_states = {
                "get_lane_vehicles": defaultdict(list),
                "get_lane_waiting_vehicle_count": defaultdict(int),
                "get_vehicle_speed": {},
                "get_vehicle_distance": {},
                "get_trafficlight_phase": {},
            }

            halting_variable = traci.constants.LAST_STEP_VEHICLE_HALTING_NUMBER
            vehicle_list_variable = traci.constants.LAST_STEP_VEHICLE_ID_LIST
            for lane_id, data in lane_results.items():
                self.system_states["get_lane_vehicles"][lane_id] = data.get(
                    vehicle_list_variable, ()
                )
                halting_count = data.get(halting_variable)
                if halting_count is not None:
                    self.system_states["get_lane_waiting_vehicle_count"][lane_id] = int(
                        halting_count
                    )

            phase_variable = getattr(traci.constants, "TL_CURRENT_PHASE", None)
            if phase_variable is not None:
                for tls_id, data in trafficlight_results.items():
                    phase_index = data.get(phase_variable)
                    if phase_index is not None:
                        self.system_states["get_trafficlight_phase"][tls_id] = int(
                            phase_index
                        )

            if self.dic_traffic_env_conf.get("ENABLE_DETAILED_LOGGING", True) and (
                full_feature_update
                or not self.dic_traffic_env_conf.get(
                    "BOUNDARY_FEATURES_IN_DETAILED_MODE", False
                )
            ):
                # Boundary tier: the per-vehicle lane/position bookkeeping
                # (segment features, arrive/left) is only consumed on
                # decision-boundary seconds; mid-window seconds record
                # speeds only, like the light path.
                lanes_with_halting_count = set(
                    self.system_states["get_lane_waiting_vehicle_count"]
                )
                for vehicle_id, data in vehicle_results.items():
                    speed = data.get(traci.constants.VAR_SPEED, 0.0)
                    lane_id = data.get(traci.constants.VAR_LANE_ID)
                    sumo_position = data.get(traci.constants.VAR_LANEPOSITION, 0.0)

                    self.system_states["get_vehicle_speed"][vehicle_id] = speed
                    # Teleporting/inserting vehicles report an empty lane id; skip
                    # them instead of counting a waiting vehicle on lane '' and
                    # making SUMO print "Lane '' is not known" on getLength.
                    if (
                        lane_id
                        and lane_id not in lanes_with_halting_count
                        and speed < 0.1
                    ):
                        self.system_states["get_lane_waiting_vehicle_count"][lane_id] += 1
                    if lane_id and lane_id not in self.lane_length:
                        try:
                            self.lane_length[lane_id] = self.traci_conn.lane.getLength(lane_id)
                        except traci.TraCIException:
                            continue
                    self.system_states["get_vehicle_distance"][vehicle_id] = sumo_position
            else:
                # Light path: only speed is subscribed. The lane-id top-up only
                # ever wrote waiting counts for internal (never-read) lanes,
                # and positions are fetched on demand by
                # refresh_vehicle_positions() for the final traffic snapshot.
                for vehicle_id, data in vehicle_results.items():
                    self.system_states["get_vehicle_speed"][vehicle_id] = data.get(
                        traci.constants.VAR_SPEED, 0.0
                    )

            if sim_vars is not None:
                now_time = float(sim_vars[2])
            else:
                now_time = float(self.traci_conn.simulation.getTime())
            self.system_states["current_time"] = now_time
            active_vehicle_ids = set(vehicle_results)
            self._seen_vehicle_ids.update(active_vehicle_ids)
            self._seen_vehicle_ids.update(departed_ids)
            self._seen_vehicle_ids.update(arrived_ids)

            # This is needed once after reset/load because checkpoint vehicles
            # do not emit a new departed event.
            if reconciled_active_vehicles:
                for vid in active_vehicle_ids:
                    if vid in self._depart_time_by_vehicle:
                        continue
                    try:
                        depart_time = float(self.traci_conn.vehicle.getDeparture(vid))
                    except (traci.TraCIException, TypeError, ValueError):
                        continue
                    if np.isfinite(depart_time) and depart_time <= now_time:
                        self._depart_time_by_vehicle[vid] = depart_time
                self._vehicle_tracking_initialized = True

            for vid in departed_ids:
                self._depart_time_by_vehicle.setdefault(vid, now_time)

            for vid in arrived_ids:
                depart_time = self._depart_time_by_vehicle.pop(vid, None)
                if depart_time is not None:
                    tt = now_time - depart_time
                    self._arrived_tt_sum += tt
                    self._arrived_count += 1
                    self._arrived_vehicle_tt[vid] = tt
                self._subscribed_vehicle_ids.discard(vid)

            self.current_time = now_time

        except traci.TraCIException as e:
            print(f"TraCIException during state update: {e}. Simulation may have ended.")
            self.close()
            raise RuntimeError(f"TraCI connection lost: {e}") from e

    def create_intersection_dict(self):
        """
        Creates the `intersection_dict` attribute for API compatibility, based on the
        dynamically discovered properties of the Intersection objects.
        """
        self.intersection_dict = {}
        print(f"Populating intersection_dict for {len(self.list_intersection)} intersections...")

        for intersection_obj in self.list_intersection:
            inter_id = intersection_obj.inter_id
            
            agent_intersection_info = {
                "id": inter_id,
                "phases": {},
                "roads": {},
                "control_phases": intersection_obj.control_phases
            }

            for phase_name, sumo_idx in intersection_obj.phase_name_2_cityflow_idx.items():
                if sumo_idx < len(intersection_obj.phases):
                    phase_def = intersection_obj.phases[sumo_idx]
                    agent_intersection_info["phases"][phase_name] = {"time": phase_def.duration, "idx": sumo_idx}

            all_roads = {**intersection_obj.incoming_roads, **intersection_obj.outgoing_roads}
            for road_id, road_obj in all_roads.items():
                is_incoming = road_id in intersection_obj.incoming_roads
                road_type = "incoming" if is_incoming else "outgoing"
                
                location_code = intersection_obj.road_id_2_orient.get(road_type, {}).get(road_id)
                location = location_dict_reverse.get(location_code)

                road_info = {
                    "location": location, "type": road_type,
                    "length": road_obj.getLength(),
                    "max_speed": road_obj.getSpeed(),
                    "num_lanes": len(road_obj.getLanes()),
                    "lanes": defaultdict(list), "go_straight": None,
                    "turn_left": None, "turn_right": None
                }
                
                if is_incoming:
                    for link in intersection_obj.road_links:
                        if link["startRoad"] == road_id:
                            turn_type = link["type"]
                            end_road_id = link["endRoad"]

                            if turn_type == "go_straight":
                                road_info["go_straight"] = end_road_id
                            elif turn_type == "turn_left":
                                road_info["turn_left"] = end_road_id
                            elif turn_type == "turn_right":
                                road_info["turn_right"] = end_road_id

                            for lane_link in link.get("laneLinks", []):
                                start_lane_idx = lane_link.get("startLaneIndex")
                                if start_lane_idx is not None and start_lane_idx not in road_info["lanes"][turn_type]:
                                    road_info["lanes"][turn_type].append(start_lane_idx)
                else:  # This is an outgoing road
                    # Expanded logic for outgoing roads
                    for link in intersection_obj.road_links:
                        if link["endRoad"] == road_id:
                            turn_type = link["type"]
                            end_road_id = link["endRoad"] # This is the same as road_id

                            # This makes the data structure consistent with incoming roads.
                            # The value will be the ID of the outgoing road itself.
                            if turn_type == "go_straight":
                                road_info["go_straight"] = end_road_id
                            elif turn_type == "turn_left":
                                road_info["turn_left"] = end_road_id
                            elif turn_type == "turn_right":
                                road_info["turn_right"] = end_road_id
                            
                            # Populate the lanes field based on the receiving lane index
                            for lane_link in link.get("laneLinks", []):
                                end_lane_idx = lane_link.get("endLaneIndex")
                                if end_lane_idx is not None and end_lane_idx not in road_info["lanes"][turn_type]:
                                    road_info["lanes"][turn_type].append(end_lane_idx)
                
                # Finalize and sort the lane lists for consistency
                road_info["lanes"] = {k: sorted(v) for k, v in road_info["lanes"].items()}
                agent_intersection_info["roads"][road_id] = road_info

            self.intersection_dict[inter_id] = agent_intersection_info

    def get_green_time(self):
        """Return the complete synchronous adaptive decision interval."""
        return int(self.dic_traffic_env_conf.get(
            "MIN_ACTION_TIME",
            15,
        ))

    def get_intersection_by_id(self, inter_id):
        for inter in self.list_intersection:
            if inter.inter_id == inter_id or inter.inter_name == inter_id:
                return inter
        return None

    def get_current_local_action(self, inter_id):
        inter = self.get_intersection_by_id(inter_id)
        if inter is None:
            return 0
        return inter.phase_index_2_action_idx.get(
            inter.current_green_phase_index,
            0,
        )

    @_seg_wrap("sumo_step")  # [SEG-TIMING] TraCI stepping + observation overhead
    def step(self, action_dict, min_action_time=None):
        """
        Apply control decisions and advance the simulation by a fixed interval.
        """
        if not self._simulation_running:
            next_state, _ = self.get_state()
            return next_state, self.get_reward(), True, {"error": "Simulation not running."}

        if min_action_time is None:
            min_action_time = self.dic_traffic_env_conf.get(
                "MIN_ACTION_TIME",
                15,
            )
        interval = self.dic_traffic_env_conf.get("INTERVAL", 1.0)
        num_inner_steps = int(min_action_time / interval)
        detailed_logging = self.dic_traffic_env_conf.get(
            "ENABLE_DETAILED_LOGGING", True
        )
        action_in_sec_display = []
        last_full = False
        # Detailed-boundary tier: like the lightweight path, full features
        # only on the final inner second; mid-window seconds keep the
        # reward-critical fields (see _update_feature).
        boundary_tier = detailed_logging and self.dic_traffic_env_conf.get(
            "BOUNDARY_FEATURES_IN_DETAILED_MODE", False
        )

        for step_idx in range(num_inner_steps):
            if not self._simulation_running: break

            # Lightweight path (and the detailed boundary tier): full
            # control-observation features only on the final inner second —
            # every env.step call ends at a decision or event boundary and
            # all feature readers act after step returns. Mid-window seconds
            # keep the per-second statistics/reward fields only. Plain
            # detailed mode keeps the legacy per-second full computation
            # because its per-second log export reads the full feature set.
            full_feature_this_second = (
                (detailed_logging and not boundary_tier)
                or step_idx == num_inner_steps - 1
            )
            last_full = full_feature_this_second

            if detailed_logging:
                # These values are used only by batch_log(). AutoAgent never
                # exports that legacy per-second state/action history.
                instant_time = self.get_current_time()
                before_action_feature = self.get_feature()
                action_in_sec_display = []
                for inter in self.list_intersection:
                    requested_action = action_dict.get(inter.inter_id, -1)
                    local_to_canonical = inter._get_four_phase()[1]
                    if requested_action != -1:
                        action = [
                            local_to_canonical.get(
                                int(requested_action),
                                int(requested_action),
                            )
                        ]
                    else:
                        current_action = inter.phase_index_2_action_idx.get(
                            inter.current_phase_index,
                            0,
                        )
                        action = [local_to_canonical.get(current_action, 0)]
                    action_in_sec_display.append(action)

            for inter in self.list_intersection:
                inter.update_previous_measurements()

            for inter in self.list_intersection:
                action = action_dict.get(inter.inter_id, -1)
                inter.set_signal(action)

            try:
                self.traci_conn.simulationStep()
            except (traci.TraCIException, traci.exceptions.FatalTraCIError) as e:
                error_message = (
                    f"TraCI connection failed during simulationStep at "
                    f"t={self.current_time}: {e}"
                )
                error_message += self._sumo_log_summary()
                print(error_message)
                self.close()
                raise RuntimeError(error_message) from e

            self._update_system_states(
                full_feature_update=full_feature_this_second
            )
            # Subscription results are only flushed by simulationStep. The
            # reset/load paths read state before any step ran, so the
            # readiness gate is flipped only here, after the first
            # post-step state update.
            self._sim_subscription_ready = self._sim_subscription_active

            for inter in self.list_intersection:
                inter.update_current_measurements(
                    self.system_states,
                    full_feature_update=full_feature_this_second,
                )

            self._update_waiting_vehicles()
            self._accumulate_intersection_queue_metrics()
            self._notify_step_listeners()

            if detailed_logging:
                # Log the pre-step state and requested action for every simulated second.
                self.log(
                    cur_time=instant_time,
                    before_action_feature=before_action_feature,
                    action=action_in_sec_display,
                )

            min_expected = getattr(self, "_last_min_expected", None)
            if min_expected is None:
                min_expected = self.traci_conn.simulation.getMinExpectedNumber()
            if min_expected == 0:
                print("Simulation ended: No more vehicles expected.")
                self.close()
                break

        if not last_full and (not detailed_logging or boundary_tier):
            # The loop exited early (simulation closed, or zero inner steps)
            # before the final inner second refreshed the full feature set.
            # Recompute from the already-updated measurements so boundary
            # consumers (get_state, get_reward, controllers, and the terminal
            # log entry ConstructSample rewards read) see a complete, current
            # feature dict. The boundary tier also left per-vehicle positions
            # empty on mid-window seconds - refill them with the one-shot
            # direct query (identical values to the subscription variable).
            if boundary_tier:
                self.refresh_vehicle_positions()
            for inter in self.list_intersection:
                inter._update_feature()

        next_state, done = self.get_state()
        reward = self.get_reward()
        if not self._simulation_running: done = True

        if detailed_logging and done and action_in_sec_display:
            terminal_time = self.get_current_time()
            last_logged_time = (
                self.list_inter_log[0][-1]["time"]
                if self.list_inter_log and self.list_inter_log[0]
                else None
            )
            if last_logged_time is None or last_logged_time < terminal_time:
                self.log(
                    cur_time=terminal_time,
                    before_action_feature=self.get_feature(),
                    action=action_in_sec_display,
                )
        
        info = {"reward": reward}
        return next_state, reward, done, info

    @_seg_wrap("sumo_step")  # [SEG-TIMING] training-mode step (same segment as step)
    def step_for_training(self, action_dict, min_action_time=None, simulator=None,
                          cluster_mapping=None, cluster_algorithm_mapping=None, rl_clusters=None):
        """
        Training mode step function that records state transitions for RL clusters.
        Records transitions at each inner step using construct_lane_states_matrix_for_cluster.
        
        Args:
            action_dict: Dictionary mapping intersection_id to action
            min_action_time: Minimum action time in seconds
            simulator: Simulator instance with intersection_graph (for state construction)
            cluster_mapping: Dict mapping cluster_id to list of intersection_ids
            cluster_algorithm_mapping: Dict mapping cluster_id to algorithm name
            rl_clusters: List of cluster_ids that use RL
            
        Returns:
            tuple: (next_state, reward, done, info)
                info contains:
                    - step_transitions: List of transition dicts, one per inner step
                      Each transition dict contains:
                        - state: Dict mapping cluster_id to state info
                        - action: Dict mapping inter_id to action
                        - next_state: Dict mapping cluster_id to next state info
                        - reward: List of rewards per intersection
        """
        if not self._simulation_running:
            next_state, _ = self.get_state()
            return next_state, self.get_reward(), True, {"error": "Simulation not running."}
        
        # Import here to avoid circular import issues
        from llm_agent.utils.model_generation_utils import (
            construct_lane_states_matrix_for_cluster,
            extract_cluster_intersection_subgraph
        )
        
        if min_action_time is None:
            min_action_time = self.dic_traffic_env_conf.get(
                "MIN_ACTION_TIME",
                15,
            )
        interval = self.dic_traffic_env_conf.get("INTERVAL", 1.0)
        num_inner_steps = int(min_action_time / interval)
        detailed_logging = self.dic_traffic_env_conf.get(
            "ENABLE_DETAILED_LOGGING", True
        )
        
        # List to store transitions for each inner step
        step_transitions = []
        masked_intersections = set()
        if cluster_mapping and cluster_algorithm_mapping:
            for cluster_id, algorithm_name in cluster_algorithm_mapping.items():
                if "RL" in algorithm_name or "Heuristic" in algorithm_name:
                    continue
                masked_intersections.update(cluster_mapping.get(cluster_id, []))
        
        # Store initial states for RL clusters before first step
        # Also collect initial RL model inputs for each intersection
        initial_cluster_states = {}
        initial_rl_inputs = {}  # {inter_id: (intersection_states, adj_matrix, target_intersection_idx)}
        if simulator and cluster_mapping and rl_clusters:
            for cluster_id in rl_clusters:
                cluster_intersections = cluster_mapping.get(cluster_id, [])
                if cluster_intersections:
                    # Use first intersection as target for state construction
                    target_inter = cluster_intersections[0]
                    try:
                        intersection_states, adj_matrix, target_idx = construct_lane_states_matrix_for_cluster(
                            simulator,
                            cluster_intersections,
                            target_inter,
                            masked_intersections=masked_intersections,
                        )
                        # Get intersection_order from extract_cluster_intersection_subgraph
                        subgraph_info = extract_cluster_intersection_subgraph(cluster_intersections, simulator)
                        intersection_order = subgraph_info.get("intersection_order", cluster_intersections)
                        
                        initial_cluster_states[cluster_id] = {
                            'lane_states': intersection_states,
                            'adj_matrix': adj_matrix,
                            'cluster_intersections': cluster_intersections,
                            'intersection_order': intersection_order
                        }
                        
                        # Collect initial RL model inputs for each intersection in this cluster
                        for inter_id in cluster_intersections:
                            if inter_id in intersection_order:
                                target_intersection_idx = intersection_order.index(inter_id)
                                initial_rl_inputs[inter_id] = (
                                    intersection_states.clone(),  # Clone to avoid reference issues
                                    adj_matrix.clone(),
                                    target_intersection_idx
                                )
                    except Exception as e:
                        print(f"Warning: Failed to construct initial state for cluster {cluster_id}: {e}")
                        initial_cluster_states[cluster_id] = None
        
        for step_idx in range(num_inner_steps):
            if not self._simulation_running:
                break
            
            instant_time = self.get_current_time()
            before_action_feature = self.get_feature() if detailed_logging else None
            
            # Store current states for RL clusters before step
            # Also collect RL model inputs for each intersection in RL clusters
            current_cluster_states = {}
            current_rl_inputs = {}  # {inter_id: (intersection_states, adj_matrix, target_intersection_idx)}
            if simulator and cluster_mapping and rl_clusters:
                for cluster_id in rl_clusters:
                    cluster_intersections = cluster_mapping.get(cluster_id, [])
                    if cluster_intersections:
                        target_inter = cluster_intersections[0]
                        try:
                            intersection_states, adj_matrix, target_idx = construct_lane_states_matrix_for_cluster(
                                simulator,
                                cluster_intersections,
                                target_inter,
                                masked_intersections=masked_intersections,
                            )
                            # Get intersection_order from extract_cluster_intersection_subgraph
                            from llm_agent.utils.model_generation_utils import extract_cluster_intersection_subgraph
                            subgraph_info = extract_cluster_intersection_subgraph(cluster_intersections, simulator)
                            intersection_order = subgraph_info.get("intersection_order", cluster_intersections)
                            
                            current_cluster_states[cluster_id] = {
                                'lane_states': intersection_states,
                                'adj_matrix': adj_matrix,
                                'cluster_intersections': cluster_intersections,
                                'intersection_order': intersection_order
                            }
                            
                            # Collect RL model inputs for each intersection in this cluster
                            for inter_id in cluster_intersections:
                                if inter_id in intersection_order:
                                    target_intersection_idx = intersection_order.index(inter_id)
                                    current_rl_inputs[inter_id] = (
                                        intersection_states.clone(),  # Clone to avoid reference issues
                                        adj_matrix.clone(),
                                        target_intersection_idx
                                    )
                        except Exception as e:
                            print(f"Warning: Failed to construct state for cluster {cluster_id} at step {step_idx}: {e}")
                            current_cluster_states[cluster_id] = None
            
            action_in_sec_display = []
            if detailed_logging:
                for inter in self.list_intersection:
                    cur_action = inter.phase_index_2_action_idx.get(
                        inter.current_phase_index, 0
                    )
                    action = [inter._get_four_phase()[1].get(cur_action, 0)]
                    action_in_sec_display.append(action)
            
            # Build action dict for this step - read current phase from intersection instances
            # This captures the actual phase being executed, not the requested action
            step_action_dict = {}
            for inter in self.list_intersection:
                if inter.inter_id in self.intersection_dict:
                    # Read current phase from intersection instance
                    cur_action = inter.phase_index_2_action_idx.get(inter.current_phase_index, 0)
                    step_action_dict[inter.inter_id] = cur_action  # Store 8-phase action index
            
            for inter in self.list_intersection:
                inter.update_previous_measurements()
            
            for inter in self.list_intersection:
                if inter.inter_id in self.intersection_dict:
                    action = action_dict.get(inter.inter_id, -1)
                    inter.set_signal(action)
            
            try:
                self.traci_conn.simulationStep()
            except traci.TraCIException as e:
                print(f'TraCIException during step: {e}. Simulation may have ended.')
                self.close()
                next_state, _ = self.get_state()
                return next_state, self.get_reward(), True, {"error": str(e)}

            self._update_system_states()
            # Keep the simulation-subscription readiness gate aligned with
            # step(): reset/load read before any step flushed results, so the
            # gate is only opened after a post-step state update.
            self._sim_subscription_ready = self._sim_subscription_active

            for inter in self.list_intersection:
                inter.update_current_measurements(self.system_states)

            self._update_waiting_vehicles()

            min_expected = getattr(self, "_last_min_expected", None)
            if min_expected is None:
                min_expected = self.traci_conn.simulation.getMinExpectedNumber()
            if min_expected == 0:
                print("Simulation ended: No more vehicles expected.")
                self.close()
                break
            
            if detailed_logging:
                self.log(
                    cur_time=instant_time,
                    before_action_feature=before_action_feature,
                    action=action_in_sec_display,
                )
            
            # Get next states for RL clusters after step
            # Also collect RL model inputs for each intersection in RL clusters
            next_cluster_states = {}
            next_rl_inputs = {}  # {inter_id: (intersection_states, adj_matrix, target_intersection_idx)}
            if simulator and cluster_mapping and rl_clusters:
                for cluster_id in rl_clusters:
                    cluster_intersections = cluster_mapping.get(cluster_id, [])
                    if cluster_intersections:
                        target_inter = cluster_intersections[0]
                        try:
                            intersection_states, adj_matrix, target_idx = construct_lane_states_matrix_for_cluster(
                                simulator,
                                cluster_intersections,
                                target_inter,
                                masked_intersections=masked_intersections,
                            )
                            # Get intersection_order from extract_cluster_intersection_subgraph
                            from llm_agent.utils.model_generation_utils import extract_cluster_intersection_subgraph
                            subgraph_info = extract_cluster_intersection_subgraph(cluster_intersections, simulator)
                            intersection_order = subgraph_info.get("intersection_order", cluster_intersections)
                            
                            next_cluster_states[cluster_id] = {
                                'lane_states': intersection_states,
                                'adj_matrix': adj_matrix,
                                'cluster_intersections': cluster_intersections,
                                'intersection_order': intersection_order
                            }
                            
                            # Collect RL model inputs for each intersection in this cluster
                            for inter_id in cluster_intersections:
                                if inter_id in intersection_order:
                                    target_intersection_idx = intersection_order.index(inter_id)
                                    next_rl_inputs[inter_id] = (
                                        intersection_states.clone(),  # Clone to avoid reference issues
                                        adj_matrix.clone(),
                                        target_intersection_idx
                                    )
                        except Exception as e:
                            print(f"Warning: Failed to construct next state for cluster {cluster_id} at step {step_idx}: {e}")
                            next_cluster_states[cluster_id] = None
            
            # Get reward for this step
            step_reward = self.get_reward()
            
            # Use initial states for first step, current states for subsequent steps
            state_for_transition = initial_cluster_states if step_idx == 0 else current_cluster_states
            
            # Store transition for this inner step
            transition = {
                'state': state_for_transition,
                'action': step_action_dict,
                'next_state': next_cluster_states,
                'reward': step_reward,
                'step_idx': step_idx,
                'time': instant_time,
                'rl_inputs': current_rl_inputs,  # RL model inputs for current state
                'next_rl_inputs': next_rl_inputs  # RL model inputs for next state
            }
            step_transitions.append(transition)
            
            # Update initial states for next iteration (use next_cluster_states as new initial)
            if next_cluster_states:
                initial_cluster_states = next_cluster_states.copy()
                initial_rl_inputs = next_rl_inputs.copy()  # Also update RL inputs
            elif current_cluster_states:
                # If next_cluster_states is empty but current exists, use current as fallback
                initial_cluster_states = current_cluster_states.copy()
                initial_rl_inputs = current_rl_inputs.copy()  # Also update RL inputs
        
        next_state, done = self.get_state()
        reward = self.get_reward()
        if not self._simulation_running:
            done = True
        
        info = {
            "reward": reward,
            "step_transitions": step_transitions
        }
        return next_state, reward, done, info

    def _update_waiting_vehicles(self):
        """ Updates the waiting time for vehicles with speed < 0.1 m/s. """
        interval = self.dic_traffic_env_conf.get("INTERVAL", 1.0)
        current_vehicle_speeds = self.system_states.get("get_vehicle_speed", {})
        self._seen_vehicle_ids.update(current_vehicle_speeds)

        for v_id in list(self.waiting_vehicle_list.keys()):
            if v_id not in current_vehicle_speeds or current_vehicle_speeds[v_id] >= 0.1:
                del self.waiting_vehicle_list[v_id]
            else:
                self.waiting_vehicle_list[v_id] += interval

        for v_id, speed in current_vehicle_speeds.items():
            self._total_waiting_time_by_vehicle.setdefault(v_id, 0.0)
            if v_id not in self.waiting_vehicle_list and speed < 0.1:
                self.waiting_vehicle_list[v_id] = interval
            if speed < 0.1:
                self._total_waiting_time_by_vehicle[v_id] += interval

    def _accumulate_intersection_queue_metrics(self):
        """Accumulate one per-second queue observation for every intersection."""
        self._queue_observation_steps += 1
        network_queue = 0.0
        for intersection in self.list_intersection:
            intersection_queue = float(sum(
                intersection.dic_feature.get(
                    "lane_num_waiting_vehicle_in",
                    [0],
                )
            ))
            network_queue += intersection_queue
            self._intersection_queue_sum += intersection_queue
            self._intersection_queue_count += 1
        self._canonical_reward_sum -= network_queue

    def add_step_listener(self, listener):
        """Register an object exposing ``on_simulation_second(env)``."""
        if listener not in self._step_listeners:
            self._step_listeners.append(listener)

    def remove_step_listener(self, listener):
        """Remove a previously registered simulation-step listener."""
        if listener in self._step_listeners:
            self._step_listeners.remove(listener)

    def _notify_step_listeners(self):
        for listener in tuple(self._step_listeners):
            listener.on_simulation_second(self)
    
    def close(self):
        """
        Closes the TraCI connection and terminates the SUMO subprocess.
        """
        if self._simulation_running and self.traci_conn:
            try:
                self.traci_conn.close()
            except traci.TraCIException: pass
            finally:
                self.traci_conn = None
                self._simulation_running = False

        if self.sumo_process:
            try:
                if self.sumo_process.poll() is None:
                    self.sumo_process.terminate()
                    self.sumo_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.sumo_process.kill()
            except Exception: pass
            finally:
                self.sumo_process = None
        
        print("SUMO Environment closed.")

    def __del__(self):
        """Ensures the simulation is closed when the object is garbage collected."""
        self.close()

    # ==========================================================================
    # API Methods (State-aware wrappers)
    # ==========================================================================

    def get_feature(self):
        """Returns a list of feature dictionaries, one for each intersection."""
        return [inter.get_feature() for inter in self.list_intersection]

    def get_state(self, list_state_feature=None):
        """Returns the current state observation for all intersections."""
        if list_state_feature is None:
            list_state_feature = self.dic_traffic_env_conf.get("LIST_STATE_FEATURE", [])

        list_state = [inter.get_state(list_state_feature) for inter in self.list_intersection]

        run_counts = self.dic_traffic_env_conf.get("RUN_COUNTS", 3600)
        # RUN_COUNTS is a duration. For rolling simulations launched with
        # SUMO --begin, current_time is absolute, so compare against the
        # absolute end of that window rather than the duration alone. Without
        # this offset, every window after t=0 terminates after its first step.
        start_time = float(getattr(self, "_start_time", 0) or 0)
        simulation_end_time = start_time + float(run_counts)
        done = (
            self.current_time >= simulation_end_time
            or not self._simulation_running
        )

        return list_state, done

    def get_reward(self):
        """Returns a list of reward values, one for each intersection."""
        reward_info = self.dic_traffic_env_conf.get("DIC_REWARD_INFO", {})
        return [inter.get_reward(reward_info) for inter in self.list_intersection]

    def get_current_time(self):
        """Returns the current simulation time."""
        return self.current_time

    def get_vehicle_count(self):
        """Gets the total number of running vehicles from SUMO."""
        if not self._simulation_running: return 0
        try: return self.traci_conn.vehicle.getIDCount()
        except traci.TraCIException: return 0

    def get_vehicles(self, include_waiting=False):
        """Gets a list of all vehicle IDs from SUMO."""
        if not self._simulation_running: return []
        try: return self.traci_conn.vehicle.getIDList()
        except traci.TraCIException: return []

    def get_lane_vehicle_count(self):
        """Gets vehicle count per lane from the last step's cached state."""
        if not self._simulation_running: return {}
        return {
            lane: len(vehicles)
            for lane, vehicles in self.system_states.get("get_lane_vehicles", {}).items()
        }

    def get_lane_waiting_vehicle_count(self):
        """Gets waiting vehicle count per lane from the last step's cached state."""
        if not self._simulation_running: return {}
        return self.system_states.get("get_lane_waiting_vehicle_count", {}).copy()

    def get_lane_vehicles(self):
        """Gets vehicle IDs per lane from the last step's cached state."""
        if not self._simulation_running: return {}
        return self.system_states.get("get_lane_vehicles", {}).copy()

    def get_vehicle_info(self, vehicle_id):
        """Gets detailed information for a specific vehicle from SUMO."""
        default_info = {"running": "false"}
        if not self._simulation_running or vehicle_id not in self.system_states.get("get_vehicle_speed", {}):
            return default_info
        try:
            return {"running": "true", "drivable": self.traci_conn.vehicle.getLaneID(vehicle_id)}
        except traci.TraCIException: return default_info

    def get_vehicle_speed(self):
        """Gets speed for all vehicles from the last step's cached state."""
        if not self._simulation_running: return {}
        return self.system_states.get("get_vehicle_speed", {}).copy()

    def get_vehicle_distance(self):
        """Gets lane positions (meters from lane start) from the last step's cached state."""
        if not self._simulation_running: return {}
        return self.system_states.get("get_vehicle_distance", {}).copy()

    def refresh_vehicle_positions(self):
        """One-shot direct query of every active vehicle's lane position.

        The light path subscribes only to vehicle speed, so
        ``system_states["get_vehicle_distance"]`` stays empty during the
        window. Call this right before consumers that need per-vehicle
        positions (the final traffic snapshot's cell_occupancy) to fill the
        dict with ``vehicle.getLanePosition`` — the one-shot equivalent of
        the VAR_LANEPOSITION subscription.
        """
        if not self._simulation_running:
            return {}
        positions = self.system_states.setdefault("get_vehicle_distance", {})
        for vehicle_id in self.system_states.get("get_vehicle_speed", {}):
            try:
                positions[vehicle_id] = float(
                    self.traci_conn.vehicle.getLanePosition(vehicle_id)
                )
            except traci.TraCIException:
                continue
        return positions

    def get_leader(self, vehicle_id):
        """Gets the leader of a specific vehicle from SUMO."""
        if not self._simulation_running: return ""
        try:
            leader_info = self.traci_conn.vehicle.getLeader(vehicle_id)
            return leader_info[0] if leader_info else ""
        except traci.TraCIException: return ""

    def get_average_travel_time(self):
        """Gets the average travel time of vehicles that have finished their trips (version-agnostic)."""
        # If simulation API supports it, use it
        sim = getattr(self.traci_conn, "simulation", None) if self.traci_conn else None
        if sim is not None and hasattr(sim, "getArrivedMeanTravelTime"):
            try:
                return sim.getArrivedMeanTravelTime()
            except (traci.TraCIException, AttributeError):
                # Fall through to internal aggregate
                pass

        # Fallback: use the internal aggregate (works even after simulation is closed)
        return float(self._arrived_tt_sum / self._arrived_count) if self._arrived_count > 0 else 0.0

    def get_arrived_vehicle_travel_times(self):
        """Returns {vehicle_id: travel_time} for all vehicles that have arrived so far."""
        return dict(self._arrived_vehicle_tt)

    def get_all_vehicle_travel_times(self):
        """Return elapsed travel time for every tracked arrived or active vehicle."""
        travel_times = dict(self._arrived_vehicle_tt)
        current_time = float(self.get_current_time())
        for vehicle_id, depart_time in self._depart_time_by_vehicle.items():
            travel_times[vehicle_id] = max(
                0.0,
                current_time - float(depart_time),
            )
        return travel_times

    def start_travel_time_measurement(self, start_time):
        """Start active-vehicle travel-time measurement at a test boundary."""
        for vehicle_id in self.system_states.get("get_vehicle_speed", {}):
            self._depart_time_by_vehicle[vehicle_id] = float(start_time)

    def get_all_vehicle_waiting_times(self):
        """Return cumulative stopped time for every vehicle observed in this run."""
        return {
            vehicle_id: float(
                self._total_waiting_time_by_vehicle.get(vehicle_id, 0.0)
            )
            for vehicle_id in self._seen_vehicle_ids
        }

    def get_intersection_queue_totals(self):
        """Return per-second network queue totals and observation counts."""
        return {
            "sum": float(self._intersection_queue_sum),
            "count": int(self._intersection_queue_count),
            "step_count": int(self._queue_observation_steps),
        }

    def set_tl_phase(self, intersection_id, phase_id):
        """Sets the traffic light phase for a specific intersection ID."""
        if not self._simulation_running: return
        try: self.traci_conn.trafficlight.setPhase(intersection_id, phase_id)
        except traci.TraCIException as e: print(f"TraCIException setting phase for {intersection_id}: {e}")
        else:
            inter = self.get_intersection_by_id(intersection_id)
            if inter is not None:
                # External phase write: the armed-duration cache no longer
                # describes SUMO's TLS state for this intersection.
                inter._armed_phase_duration_expiry = None
                inter._armed_phase_duration_phase = None

    def set_vehicle_speed(self, vehicle_id, speed):
        """Sets the speed for a specific vehicle."""
        if not self._simulation_running: return
        try: self.traci_conn.vehicle.setSpeed(vehicle_id, speed)
        except traci.TraCIException as e: print(f"TraCIException setting speed for vehicle {vehicle_id}: {e}")

    def set_vehicle_route(self, vehicle_id, route):
        """Changes the route of a specific vehicle."""
        if not self._simulation_running: return False
        try:
            self.traci_conn.vehicle.setRoute(vehicle_id, route)
            return True
        except traci.TraCIException as e:
            print(f"TraCIException setting route for vehicle {vehicle_id}: {e}")
            return False

    def set_random_seed(self, seed):
        """No-op for SUMO. The seed must be set at simulation start via reset()."""
        print("Warning: `set_random_seed` has no effect after the simulation has started. Provide a seed to `env.reset()`.")

    def snapshot(self, path=None):
        """Takes a snapshot of the current simulation state."""
        if not self._simulation_running:
            return None
        try:
            snapshot_path = path if path else os.path.join(self.path_to_log, f"snapshot_{self.current_time}.xml")
            self.traci_conn.simulation.saveState(snapshot_path)
            return snapshot_path
        except traci.TraCIException as e:
            print(f"TraCIException taking snapshot: {e}")
            return None

    def load_from_file(self, path):
        """Loads a simulation state from a snapshot file."""
        if not self._simulation_running:
            print("Warning: Cannot load state. Simulation not running.")
            return
        try:
            self.traci_conn.simulation.loadState(path)
            self._post_load_reset()
            print(f"Simulation state loaded from file: {path}")
        except Exception as e:
            print(f"Error loading snapshot from file {path}: {e}")
            
    def _post_load_reset(self):
        """Resets internal state after loading a snapshot."""
        print("Resetting internal state after loading snapshot...")
        self.current_time = self.traci_conn.simulation.getTime()
        self._subscribed_vehicle_ids = set()
        self._vehicle_tracking_initialized = False
        self._vehicle_subscription_reconcile_needed = False
        for inter in self.list_intersection:
            # loadState may move TLS programs; drop stale armed-duration
            # knowledge so set_signal re-arms on the next hold.
            inter._armed_phase_duration_expiry = None
            inter._armed_phase_duration_phase = None
        # loadState is not a simulation step and may drop subscriptions, so
        # re-subscribe and force direct queries until the next step flushes
        # fresh subscription results.
        self._subscribe_trafficlight_phases()
        self._subscribe_simulation_domain()
        self._update_system_states()
        for inter in self.list_intersection:
            inter.update_current_measurements(self.system_states)
        self._update_waiting_vehicles()

    def log(self, cur_time, before_action_feature, action):
        """Logs the state and action for each intersection."""
        for inter_ind in range(len(self.list_intersection)):
            self.list_inter_log[inter_ind].append({
                "time": cur_time,
                "state": before_action_feature[inter_ind],
                "action": action[inter_ind]
            })

    def batch_log(self, start=0, stop=None):
        """Logs vehicle times and intersection state-action logs."""
        if stop is None: stop = len(self.list_intersection)
        for inter_ind in range(start, stop):
            inter = self.list_intersection[inter_ind]
            # Log vehicle data
            path_to_vehicle_log = os.path.join(self.path_to_log, f"vehicle_{inter.inter_name}.csv")
            dic_vehicle = inter.get_dic_vehicle_arrive_leave_time()
            if dic_vehicle:
                pd.DataFrame.from_dict(dic_vehicle, orient="index").to_csv(path_to_vehicle_log, na_rep="nan", index_label="vehicle_id")
            # Log state-action data
            path_to_state_log = os.path.join(self.path_to_log, f"inter_{inter_ind}.pkl")
            with open(path_to_state_log, "wb") as f:
                pickle.dump(self.list_inter_log[inter_ind], f)

    def bulk_log_multi_process(self, batch_size=100):
        """
        Uses multiple processes to speed up logging (if I/O bound).
        Calls batch_log for different ranges in parallel.
        """
        num_intersections = len(self.list_intersection)
        if num_intersections == 0:
            print("No intersections to log.")
            return

        actual_batch_size = min(batch_size, num_intersections) if batch_size > 0 else num_intersections
        print(f"Starting bulk log using multiprocessing (batch size: {actual_batch_size})...")
        start_time = time.time()

        process_list = []
        for batch_start in range(0, num_intersections, actual_batch_size):
            batch_stop = min(batch_start + actual_batch_size, num_intersections)
            # Create and start a process for the self.batch_log method
            p = Process(target=self.batch_log, args=(batch_start, batch_stop))
            p.start()
            process_list.append(p)
            print(f"  Started logging process for intersections {batch_start}-{batch_stop - 1}")

        print("Waiting for logging processes to complete...")
        for i, p in enumerate(process_list):
            p.join()  # Wait for each process to finish
            print(f"  Logging process {i + 1}/{len(process_list)} completed.")

        print(f"Finished bulk log using multiprocessing in {time.time() - start_time:.2f}s")

    def end_engine(self):
        """Close the running SUMO/TraCI process at the end of a rollout."""
        self.close()
        print("================ SUMO Process End ================")

    def __deepcopy__(self, memo):
        """
        Custom deepcopy implementation for SUMOEnv.
        This method creates a copy of the Python-side environment state,
        while nullifying attributes that cannot or should not be copied,
        such as the live TraCI connection and the SUMO process handle.
        The static network object (`sumo_net`) is shared by reference.
        """
        if id(self) in memo:
            return memo[id(self)]

        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result

        for k, v in self.__dict__.items():
            # Skip non-serializable or shared attributes
            if k in ['sumo_process', 'traci_conn', 'sumo_net']:
                continue
            # Perform a deepcopy on all other attributes
            setattr(result, k, deepcopy(v, memo))

        # Manually handle the skipped attributes for the new copy
        result.sumo_process = None
        result.traci_conn = None
        result.sumo_net = self.sumo_net  # Share the reference to the static network data

        return result
