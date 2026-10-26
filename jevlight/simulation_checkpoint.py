"""Atomic local checkpoints at completed controller-step boundaries.

The caller must stop decision/recording threads before saving. Restoring requires
a fresh SUMOEnv reset with ``load_state_path=checkpoint.sumo_path`` and a separate
startup log directory, so constructing intersections cannot truncate old logs.
Output tails are rejected rather than silently deleted or counted twice.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

import numpy as np


ENV_FIELDS = (
    "current_time", "system_states", "waiting_vehicle_list", "_seen_vehicle_ids",
    "_total_waiting_time_by_vehicle", "_intersection_queue_sum",
    "_intersection_queue_count", "_queue_observation_steps", "_depart_time_by_vehicle",
    "_arrived_tt_sum", "_arrived_count", "_arrived_vehicle_tt", "_canonical_reward_sum",
    "_last_min_expected", "list_inter_log",
)
INTERSECTION_FIELDS = (
    "yellow_phase_index", "pending_target_phase_index", "yellow_start_time",
    "is_in_yellow_phase", "dic_lane_vehicle_current_step",
    "dic_lane_waiting_vehicle_count_current_step", "dic_vehicle_speed_current_step",
    "dic_vehicle_distance_current_step", "dic_lane_vehicle_current_step_in",
    "list_lane_vehicle_previous_step_in", "list_lane_vehicle_current_step_in",
    "dic_vehicle_arrive_leave_time", "dic_feature", "_current_sim_time",
    "current_phase_index", "default_phase_index", "previous_phase_index",
    "next_phase_to_set_index", "current_green_phase_index", "current_phase_duration",
    "time_since_last_change", "_armed_phase_duration_expiry", "_armed_phase_duration_phase",
    "fixed_time_cycle_index",
)
CONTROLLER_FIELDS = (
    "cooperative_states", "previous_signals", "total_input_tokens", "total_output_tokens",
    "total_requests", "total_failures", "total_rate_limited", "latencies",
)
RECORDER_FIELDS = (
    "start_time", "next_checkpoint_time", "hourly_records", "window_records",
    "_wandb_window_records", "_logged_hour_count", "_logged_window_count",
    "_final_record", "_final_logged",
)


def encode(value):
    """JSON value codec preserving tuple keys, sets and counting factories."""
    if isinstance(value, np.ndarray):
        return ["array", value.dtype.str, encode(value.tolist())]
    if isinstance(value, np.generic):
        return encode(value.item())
    if isinstance(value, dict):
        tag = "counter" if isinstance(value, Counter) else "dict"
        factory = None
        if isinstance(value, defaultdict):
            factories = {int: "int", list: "list", Counter: "counter"}
            if value.default_factory not in factories:
                raise TypeError("Unsupported checkpoint defaultdict factory")
            tag, factory = "defaultdict", factories[value.default_factory]
        return [tag, factory, [[encode(k), encode(v)] for k, v in value.items()]]
    for kind, name in ((tuple, "tuple"), (list, "list"), (set, "set"), (frozenset, "frozenset")):
        if isinstance(value, kind):
            return [name, [encode(v) for v in value]]
    if type(value) is float and not math.isfinite(value):
        return ["float", "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")]
    if value is None or type(value) in (str, int, float, bool):
        return ["scalar", value]
    raise TypeError(f"Unsupported checkpoint state: {type(value).__name__}")


def decode(value):
    tag = value[0]
    if tag == "scalar":
        return value[1]
    if tag == "float":
        return {"nan": math.nan, "inf": math.inf, "-inf": -math.inf}[value[1]]
    if tag == "array":
        dtype = np.dtype(value[1])
        if dtype.hasobject:
            raise ValueError("Object arrays are not checkpoint state")
        return np.array(decode(value[2]), dtype=dtype)
    if tag in ("dict", "counter", "defaultdict"):
        result = dict((decode(k), decode(v)) for k, v in value[2])
        if tag == "counter":
            return Counter(result)
        if tag == "defaultdict":
            return defaultdict({"int": int, "list": list, "counter": Counter}[value[1]], result)
        return result
    if tag in ("tuple", "list", "set", "frozenset"):
        return {"tuple": tuple, "list": list, "set": set, "frozenset": frozenset}[tag](
            decode(v) for v in value[1])
    raise ValueError(f"Unknown checkpoint state tag: {tag}")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_identity(paths):
    return {str(Path(p).resolve()): sha256(p) for p in paths}


def runtime_identity():
    """Probe the actual runtime before acquiring or modifying run outputs.

    SUMOEnv launches ``sumo`` from PATH. Use that same executable here, and
    preserve loader/probe errors instead of discovering them after archiving
    the previous attempt. This starts no simulation and uses no GPU.
    """
    executable = shutil.which("sumo")
    if executable is None:
        raise FileNotFoundError("Checkpoint runtime preflight: 'sumo' not found in PATH")
    probe = subprocess.run([executable, "--version"], capture_output=True,
                           text=True, timeout=15)
    if probe.returncode:
        raise RuntimeError(f"SUMO runtime preflight exited {probe.returncode}: "
                           f"{probe.stdout}\n{probe.stderr}")
    if not probe.stdout.strip():
        raise RuntimeError("SUMO runtime preflight returned no version")
    dependencies = {}
    for name in ("numpy", "pandas", "traci", "sumolib", "requests", "tqdm", "typesafe-sdk"):
        module = importlib.import_module(name.replace("-", "_"))
        dependencies[name] = {"version": importlib.metadata.version(name),
                              "module": file_identity([module.__file__])}
    return {"python": sys.version, "executable": file_identity([sys.executable]),
            "dependencies": dependencies,
            "sumo": {"binary": file_identity([executable]),
                     "version": probe.stdout.strip(), "stderr": probe.stderr.strip()}}


def _fields(obj, names):
    return {name: getattr(obj, name) for name in names}


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


class OutputLease:
    """Nonblocking ownership of one run's outputs for its entire lifetime.

    All writers and resume callers must acquire this before opening outputs.
    The persistent lock file must never be unlinked, including after a crash.
    The kernel releases ownership on process exit; PID files are not locks.
    """

    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self._stream = None
        self._pid = None

    def __enter__(self):
        import fcntl

        if self._stream is not None:
            raise RuntimeError("Output lease already acquired")
        self.directory.mkdir(parents=True, exist_ok=True)
        stream = (self.directory / ".simulation-output.lock").open("a+b")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stream.close()
            raise RuntimeError(f"Simulation output is already owned: {self.directory}") from None
        self._stream, self._pid = stream, os.getpid()
        return self

    def require(self, paths):
        if self._stream is None or self._pid != os.getpid():
            raise RuntimeError("An active output lease owned by this process is required")
        for path in paths:
            if not Path(path).resolve().is_relative_to(self.directory):
                raise ValueError(f"Output is outside the leased run directory: {path}")

    def __exit__(self, *exc):
        # Closing the descriptor also releases flock. A forked child must not
        # explicitly unlock the parent's shared open-file description.
        self._stream.close()
        self._stream, self._pid = None, None


def _prefix_sha256(path, size):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        remaining = size
        while remaining:
            block = stream.read(min(remaining, 1024 * 1024))
            if not block:
                raise ValueError(f"Output is shorter than checkpoint boundary: {path}")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def _archive_output_tails(outputs, *, lease, checkpoint_path):
    """Preserve full post-checkpoint attempts before restoring append prefixes.

    All prefixes are checked before the first output mutation. A failed archive
    or partial prefix installation remains on disk; retrying this explicit
    operation accepts already restored prefixes and preserves remaining tails.
    This does not silently recover corrupt or missing committed data.
    """
    lease.require(outputs)
    changed = {}
    for filename, boundary in outputs.items():
        path = Path(filename)
        size = boundary["size"]
        if type(size) is not int or size < 0:
            raise ValueError("Invalid checkpoint output size")
        if _prefix_sha256(path, size) != boundary["sha256"]:
            raise ValueError(f"Output committed prefix mismatch: {path}")
        if path.stat().st_size != size:
            changed[filename] = boundary
    if not changed:
        return None
    archive_root = lease.directory / ".resume-archives"
    archive_root.mkdir(exist_ok=True)
    archive = archive_root / ("segment-" + uuid.uuid4().hex)
    archive.mkdir()
    records = {}
    for index, (filename, boundary) in enumerate(changed.items()):
        source = Path(filename)
        saved = archive / f"output-{index}"
        with source.open("rb") as src, saved.open("xb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        if _prefix_sha256(saved, boundary["size"]) != boundary["sha256"]:
            raise ValueError(f"Output changed while archiving: {source}")
        records[filename] = {"archive_file": saved.name, "size": saved.stat().st_size,
                             "sha256": sha256(saved), "committed": boundary}
    # The complete originals and their provenance are durable before replacing
    # any live file. Never overwrite/delete a prior failed or successful segment.
    _write_json(archive / "manifest.json", {"checkpoint": str(checkpoint_path),
                                            "outputs": records})
    _sync_dir(archive)
    _sync_dir(archive_root)
    _sync_dir(lease.directory)
    for filename, record in records.items():
        if sha256(filename) != record["sha256"]:
            raise ValueError(f"Output changed while archiving: {filename}")
    for filename, record in records.items():
        path = Path(filename)
        temporary = path.with_name(".resume-prefix-" + uuid.uuid4().hex)
        with (archive / record["archive_file"]).open("rb") as src, temporary.open("xb") as dst:
            remaining = record["committed"]["size"]
            while remaining:
                block = src.read(min(remaining, 1024 * 1024))
                if not block:
                    raise ValueError("Archived output unexpectedly truncated")
                dst.write(block)
                remaining -= len(block)
            dst.flush()
            os.fsync(dst.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
        _sync_dir(path.parent)
    _write_json(archive / "restored.json", {"outputs": list(records)})
    _sync_dir(archive)
    return archive


def controller_identity(controller):
    names = ("phase_duration", "packaging", "fallback", "min_confidence", "speculative",
             "max_workers", "agent_mode")
    client = getattr(controller, "client", None)
    client_names = ("transport", "model", "base_url", "timeout", "max_retries",
                    "min_interval", "mock", "batch_size")
    return {"class": type(controller).__name__,
            **{name: getattr(controller, name) for name in names if hasattr(controller, name)},
            "client": ({name: getattr(client, name) for name in client_names}
                       if client is not None else None)}


def _environment_identity(env):
    # lane_length is derived from the already-hashed network; runtime paths and
    # connection-local subscription handles are deliberately not state identity.
    return encode({"config": {key: value for key, value in
                              getattr(env, "dic_traffic_env_conf", {}).items()
                              if key != "lane_length"},
                   "phase_mapping": getattr(env, "inter_phase_mapping", {})})


def save_checkpoint(root, *, env, controller, loop, identity, append_paths, recorder=None):
    """Commit an immutable SUMO+Python generation, then atomically publish it.

    ``identity`` must include resolved experiment parameters, input/code hashes,
    and backend/weight identity. No client objects or credentials are serialized.
    ``loop`` retains step, total_reward, done, max_steps and evaluation start/end.
    """
    if not env._simulation_running:
        raise ValueError("Cannot checkpoint a stopped SUMO instance")
    if not identity or int(loop["step"]) < 0:
        raise ValueError("Checkpoint requires identity and a valid completed step")
    if float(env.get_current_time()) != float(env.current_time):
        raise ValueError("SUMO/Python time mismatch")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    generation = root / ("checkpoint-" + uuid.uuid4().hex)
    generation.mkdir()
    # Leave failed generations in place for diagnosis; they never become latest.
    sumo_path = generation / "sumo.xml"
    env.traci_conn.simulation.saveState(str(sumo_path))
    tree = ET.parse(sumo_path)
    if not any("rng" in element.tag.lower() for element in tree.iter()):
        raise ValueError("SUMO snapshot lacks RNG state; enable --save-state.rng at startup")
    with sumo_path.open("rb") as stream:
        os.fsync(stream.fileno())
    outputs = {}
    for filename in append_paths:
        path = Path(filename).resolve()
        # Caller has flushed writers; fsync before publishing byte boundaries.
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
        outputs[str(path)] = {"size": path.stat().st_size, "sha256": sha256(path)}
    state = {
        "env": _fields(env, ENV_FIELDS),
        "intersections": {i.inter_id: _fields(i, INTERSECTION_FIELDS) for i in env.list_intersection},
        "controller": _fields(controller, CONTROLLER_FIELDS),
        "relations": (vars(controller.trajectory_relations)
                      if controller.trajectory_relations is not None else None),
        "recorder": _fields(recorder, RECORDER_FIELDS) if recorder else None,
        "loop": loop, "random": random.getstate(), "numpy_random": np.random.get_state(),
        "env_start_time": getattr(env, "_start_time", 0),
        "client_last_request_time": getattr(getattr(controller, "client", None),
                                            "_last_request_time", None),
    }
    _write_json(generation / "python.json", encode(state))
    manifest = {
        "schema": 1, "identity": identity, "controller": controller_identity(controller),
        "sumo_version": list(env.traci_conn.getVersion()),
        "environment": _environment_identity(env),
        "time": env.current_time, "outputs": outputs,
        "files": {name: sha256(generation / name) for name in ("sumo.xml", "python.json")},
        "recorder": ({"total_duration": recorder.total_duration,
                      "hourly_interval": recorder.hourly_interval, "metadata": recorder.metadata,
                      "output_dir": str(recorder.output_dir.resolve())} if recorder else None),
    }
    _write_json(generation / "manifest.json", manifest)
    _sync_dir(generation)
    pointer = root / (".latest-" + uuid.uuid4().hex + ".json")
    _write_json(pointer, {"generation": generation.name,
                          "manifest_sha256": sha256(generation / "manifest.json")})
    os.replace(pointer, root / "latest.json")
    _sync_dir(root)
    return generation


def checkpoint_manifest(root):
    """Read authenticated routing metadata without opening any run output."""
    root = Path(root).resolve()
    pointer = json.loads((root / "latest.json").read_text())
    name = pointer["generation"]
    if Path(name).name != name or not name.startswith("checkpoint-"):
        raise ValueError("Invalid checkpoint generation")
    path = root / name
    if sha256(path / "manifest.json") != pointer["manifest_sha256"]:
        raise ValueError("Checkpoint manifest hash mismatch")
    return path, json.loads((path / "manifest.json").read_text())


class SimulationCheckpoint:
    """Validate before starting SUMO or opening any original output for writing."""

    def __init__(self, root, *, identity, output_lease=None, archive_tails=False):
        self.path, self.manifest = checkpoint_manifest(root)
        if self.manifest["schema"] != 1 or self.manifest["identity"] != identity:
            raise ValueError("Checkpoint configuration/input/code identity mismatch")
        if set(self.manifest["files"]) != {"sumo.xml", "python.json"}:
            raise ValueError("Checkpoint state file set mismatch")
        for name, digest in self.manifest["files"].items():
            if name not in ("sumo.xml", "python.json") or sha256(self.path / name) != digest:
                raise ValueError("Checkpoint state hash mismatch")
        self.state = decode(json.loads((self.path / "python.json").read_text()))
        self.sumo_path = self.path / "sumo.xml"
        self.output_archive = None
        if archive_tails:
            if output_lease is None:
                raise RuntimeError("Archiving output tails requires exclusive output ownership")
            self.output_archive = _archive_output_tails(
                self.manifest["outputs"], lease=output_lease, checkpoint_path=self.path)
        self.validate_outputs()

    def validate_outputs(self):
        for filename, boundary in self.manifest["outputs"].items():
            path = Path(filename)
            if (not path.is_file() or path.stat().st_size != boundary["size"]
                    or sha256(path) != boundary["sha256"]):
                raise ValueError(f"Output append boundary mismatch: {path}")

    def restore_python(self, *, env, controller, recorder=None):
        """Restore after fresh reset(load_state_path=...), without advancing time."""
        self.validate_outputs()
        if controller_identity(controller) != self.manifest["controller"]:
            raise ValueError("Controller configuration mismatch")
        if _environment_identity(env) != self.manifest["environment"]:
            raise ValueError("Environment configuration mismatch")
        if list(env.traci_conn.getVersion()) != self.manifest["sumo_version"]:
            raise ValueError("SUMO version mismatch")
        if float(env.get_current_time()) != float(self.manifest["time"]):
            raise ValueError("SUMO checkpoint time mismatch")
        if [i.inter_id for i in env.list_intersection] != list(self.state["intersections"]):
            raise ValueError("Intersection identity/order mismatch")
        expected_recorder = self.manifest["recorder"]
        actual_recorder = ({"total_duration": recorder.total_duration,
                            "hourly_interval": recorder.hourly_interval, "metadata": recorder.metadata,
                            "output_dir": str(recorder.output_dir.resolve())} if recorder else None)
        if actual_recorder != expected_recorder:
            raise ValueError("Rolling recorder configuration mismatch")
        if (controller.trajectory_relations is None) != (self.state["relations"] is None):
            raise ValueError("Co relation state mismatch")
        for key, value in self.state["env"].items():
            setattr(env, key, value)
        env._start_time = self.state["env_start_time"]
        for inter in env.list_intersection:
            vars(inter).update(self.state["intersections"][inter.inter_id])
        vars(controller).update(self.state["controller"])
        if self.state["client_last_request_time"] is not None:
            controller.client._last_request_time = self.state["client_last_request_time"]
        if controller.trajectory_relations is not None:
            vars(controller.trajectory_relations).update(self.state["relations"])
        if recorder:
            vars(recorder).update(self.state["recorder"])
            env.add_step_listener(recorder)
        # reset(load_state_path) established fresh subscriptions. Their flags and
        # connection-local handles must not be copied from the old process.
        random.setstate(self.state["random"])
        np.random.set_state(self.state["numpy_random"])
        return dict(self.state["loop"])
