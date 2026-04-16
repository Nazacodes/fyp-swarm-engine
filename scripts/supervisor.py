#!/usr/bin/env python
"""Run monitor + swarm nodes with auto-restart for stale nodes."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict


ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _new_console_flag() -> int:
    return getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def _spawn(cmd: list[str], env: Dict[str, str], log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("a", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        creationflags=_new_console_flag(),
    )


def _state_count(port: int) -> Dict[str, Dict]:
    url = f"http://localhost:{port}/api/state"
    with urllib.request.urlopen(url, timeout=2.0) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    nodes = payload.get("nodes", [])
    out = {}
    for n in nodes:
        node_id = n.get("node_id")
        if node_id:
            out[node_id] = n
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Swarm supervisor")
    parser.add_argument("--nodes", type=int, default=20)
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--groups", type=int, default=1)
    parser.add_argument("--enable-beacon", action="store_true", default=True)
    parser.add_argument("--discovery-port", type=int, default=5679)
    parser.add_argument("--batch-wait", type=float, default=5.0)
    parser.add_argument("--heartbeat-interval", type=float, default=0.7)
    parser.add_argument("--tick-seconds", type=float, default=0.7)
    args = parser.parse_args()

    os.chdir(ROOT)
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    for old in logs_dir.glob("node*.log"):
        old.unlink(missing_ok=True)

    base_env = os.environ.copy()
    base_env["MESSAGING_MODE"] = "rabbitmq"
    base_env["RABBIT_HOST"] = "localhost"
    base_env["RABBIT_USER"] = "guest"
    base_env["RABBIT_PASSWORD"] = "guest"
    base_env["TICK_SECONDS"] = str(args.tick_seconds)
    base_env["HEARTBEAT_INTERVAL"] = str(args.heartbeat_interval)

    processes: Dict[str, subprocess.Popen] = {}
    monitor_env = base_env.copy()
    monitor_env["EXPECTED_NODE_COUNT"] = str(args.nodes)
    monitor = _spawn(
        [PY, "src/web_monitor.py", "--host", "0.0.0.0", "--port", str(args.port)],
        monitor_env,
        logs_dir / "monitor.log",
    )
    print(f"Monitor started on http://localhost:{args.port}")
    time.sleep(2.0)

    beacon = None
    if args.enable_beacon:
        beacon = _spawn(
            [
                PY,
                "scripts/swarm_beacon.py",
                "--rabbit-host",
                "localhost",
                "--rabbit-port",
                "5672",
                "--monitor-port",
                str(args.port),
                "--discovery-port",
                str(args.discovery_port),
            ],
            base_env,
            logs_dir / "beacon.log",
        )
        print(f"Discovery beacon active on UDP {args.discovery_port}")

    def start_node(i: int) -> None:
        node_id = f"node{i}"
        env = base_env.copy()
        env["NODE_ID"] = node_id
        env["PEER_PORT"] = str(9300 + i)
        group_index = ((i - 1) % max(1, args.groups)) + 1
        env["GROUP_ID"] = f"zone_{group_index}"
        cfg = ROOT / "nodes" / "configs" / f"config_node{i}.json"
        if not cfg.exists():
            print(f"[warn] Missing config for {node_id}: expected {cfg}. Starting with env defaults.")
            cmd = [PY, "src/node.py"]
        else:
            cmd = [PY, "src/node.py", "--config", str(cfg)]
        processes[node_id] = _spawn(cmd, env, logs_dir / f"{node_id}.log")

    for i in range(1, args.nodes + 1):
        start_node(i)
        time.sleep(0.7)
        if i % args.batch_size == 0:
            print(f"Started {i}/{args.nodes} nodes; waiting {args.batch_wait:.1f}s")
            time.sleep(args.batch_wait)

    running = True

    def _stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print("Supervisor active. Press Ctrl+C to stop.")
    try:
        while running:
            time.sleep(6.0)
            if monitor.poll() is not None:
                print("Monitor exited unexpectedly; restarting")
                monitor = _spawn(
                    [PY, "src/web_monitor.py", "--host", "0.0.0.0", "--port", str(args.port)],
                    monitor_env,
                    logs_dir / "monitor.log",
                )
                time.sleep(2.0)

            try:
                state = _state_count(args.port)
            except Exception:
                continue

            fresh = 0
            stale_ids = []
            for i in range(1, args.nodes + 1):
                node_id = f"node{i}"
                node_state = state.get(node_id, {})
                freshness = node_state.get("freshness")
                temp = node_state.get("temp")
                proc = processes.get(node_id)
                proc_dead = (proc is None) or (proc.poll() is not None)
                if freshness == "fresh":
                    fresh += 1
                if proc_dead or freshness == "stale" or temp is None:
                    stale_ids.append(node_id)

            if stale_ids:
                print(f"Fresh={fresh}/{args.nodes}; restarting stale/dead: {', '.join(stale_ids[:8])}{'...' if len(stale_ids) > 8 else ''}")
            else:
                print(f"Fresh={fresh}/{args.nodes}; all healthy")

            for node_id in stale_ids:
                i = int(node_id.replace("node", ""))
                proc = processes.get(node_id)
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                time.sleep(0.2)
                start_node(i)
                time.sleep(0.25)
    finally:
        for proc in processes.values():
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
        try:
            if monitor.poll() is None:
                monitor.terminate()
        except Exception:
            pass
        try:
            if beacon is not None and beacon.poll() is None:
                beacon.terminate()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
