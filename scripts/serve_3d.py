#!/usr/bin/env python3
"""3D SUMO visualizer: run (or attach to) a standalone SUMO and stream it
to the JS frontend in ``viz/``.

Open ``http://127.0.0.1:8300`` — the page renders the road network in 3D
(three.js) with live vehicles and traffic-light states.

The server core lives in ``jevlight/viz_server.py`` (shared with
``run_jevlight.py --visualize``); this CLI drives it with its own SUMO.

Examples:
    python scripts/serve_3d.py                     # Jinan, realtime
    python scripts/serve_3d.py --speed 4 --count 3600
    python scripts/serve_3d.py --attach 127.0.0.1:8813
"""

from __future__ import annotations

import argparse
import shlex
import threading
from pathlib import Path
from typing import Optional, Sequence, Tuple

from jevlight.viz_server import (
    DEFAULT_VIZ_DIR,
    DEFAULT_VIZ_HOST,
    DEFAULT_VIZ_PORT,
    NetworkModel,
    SumoRuntime,
    make_viz_server,
)

TRACI_LABEL = "jevlight3d"


def resolve_scenario_paths(args: argparse.Namespace) -> Tuple[str, str]:
    if args.net and args.routes:
        return args.net, args.routes
    from jevlight.config import setup_dataset_config

    dataset_config = setup_dataset_config(args.dataset)
    base = Path("data") / dataset_config["template"] / str(dataset_config["road_net"])
    net = args.net or str(base / dataset_config["roadnet_file"])
    routes = args.routes or str(base / args.traffic_file)
    return net, routes


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="3D SUMO visualizer: bridge a live simulation to viz/"
    )
    parser.add_argument("--dataset", default="jinan")
    parser.add_argument("--traffic_file", default="anon_3_4_jinan_real.rou.xml")
    parser.add_argument("--net", default=None, help="Override the .net.xml path")
    parser.add_argument("--routes", default=None, help="Override the route file")
    parser.add_argument("--sumo_binary", default="sumo")
    parser.add_argument(
        "--sumo_args",
        default="",
        help='Extra SUMO arguments, shell-split (e.g. "--seed 3")',
    )
    parser.add_argument(
        "--attach",
        default=None,
        help="Attach to a running SUMO (host:port) instead of launching one",
    )
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--count", type=int, default=0, help="Stop stepping after N steps")
    parser.add_argument("--host", default=DEFAULT_VIZ_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_VIZ_PORT)
    parser.add_argument("--viz_dir", default=str(DEFAULT_VIZ_DIR))
    args = parser.parse_args(argv)

    net_path, route_path = resolve_scenario_paths(args)
    network = NetworkModel.load(net_path)
    print(
        f"[viz] network {net_path}: {len(network.payload['lanes'])} lanes, "
        f"{len(network.payload['tls'])} traffic lights",
        flush=True,
    )

    if args.attach:
        import traci

        host, _, port = args.attach.partition(":")
        traci.connect(host, int(port), label=TRACI_LABEL)
        conn = traci.getConnection(TRACI_LABEL)
        print(f"[viz] attached to SUMO at {args.attach}", flush=True)
    else:
        import traci

        cmd = [
            args.sumo_binary,
            "--net-file", net_path,
            "--route-files", route_path,
            "--no-step-log", "true",
        ] + shlex.split(args.sumo_args)
        print(f"[viz] starting SUMO: {' '.join(cmd)}", flush=True)
        # traci.start returns the handshake results, not the connection.
        traci.start(cmd, label=TRACI_LABEL)
        conn = traci.getConnection(TRACI_LABEL)
    step_length = float(conn.simulation.getDeltaT())

    runtime = SumoRuntime(
        conn,
        step_length=step_length,
        speed=args.speed,
        offset=tuple(network.payload["offset"]),  # type: ignore[arg-type]
        max_steps=args.count,
    )
    thread = threading.Thread(target=runtime.run, name="sumo-runtime", daemon=True)
    thread.start()

    server = make_viz_server(
        runtime, network.payload, Path(args.viz_dir), args.host, args.port
    )
    print(
        f"[viz] open http://{args.host}:{args.port} (Ctrl-C stops the simulation)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
        thread.join(timeout=5)
        server.server_close()


if __name__ == "__main__":
    main()
