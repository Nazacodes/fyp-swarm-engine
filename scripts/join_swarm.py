#!/usr/bin/env python
"""Auto-discover swarm host and join with a node.

Designed for Raspberry Pi/edge nodes:
1) Broadcast discovery request
2) Parse host beacon response
3) Launch src/node.py with discovered RabbitMQ host
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional


ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_PORT = 5679


def discover_swarm(timeout_seconds: float = 8.0, discovery_port: int = DISCOVERY_PORT) -> Optional[Dict]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.8)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            sock.sendto(b"SWARM_DISCOVERY_REQUEST", ("255.255.255.255", discovery_port))
            data, addr = sock.recvfrom(4096)
            payload = json.loads(data.decode("utf-8"))
            if "rabbit_host" in payload:
                payload["host_addr"] = addr[0]
                return payload
        except socket.timeout:
            continue
        except Exception:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover swarm and join as node")
    parser.add_argument("--node-id", default="pi-node1")
    parser.add_argument("--group-id", default="zone_2")
    parser.add_argument("--config", default=None)
    parser.add_argument("--messaging-mode", default="rabbitmq")
    parser.add_argument("--discovery-timeout", type=float, default=8.0)
    parser.add_argument("--discovery-port", type=int, default=DISCOVERY_PORT)
    parser.add_argument("--rabbit-user", default="guest")
    parser.add_argument("--rabbit-password", default="guest")
    parser.add_argument("--protocol-mode", default="ip")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    info = discover_swarm(timeout_seconds=args.discovery_timeout, discovery_port=args.discovery_port)
    if not info:
        print("No swarm beacon found on LAN. Ensure host is running scripts/supervisor.py.")
        return 2

    rabbit_host = str(info.get("rabbit_host"))
    rabbit_port = str(info.get("rabbit_port", 5672))
    print(f"Discovered swarm '{info.get('swarm_name', 'unknown')}' at rabbit={rabbit_host}:{rabbit_port}")

    env = os.environ.copy()
    env["NODE_ID"] = args.node_id
    env["GROUP_ID"] = args.group_id
    env["MESSAGING_MODE"] = args.messaging_mode
    env["RABBIT_HOST"] = rabbit_host
    env["RABBIT_PORT"] = rabbit_port
    env["RABBIT_USER"] = args.rabbit_user
    env["RABBIT_PASSWORD"] = args.rabbit_password
    env["PROTOCOL_MODE"] = args.protocol_mode

    node_cmd = [sys.executable, str(ROOT / "src" / "node.py")]
    if args.config:
        node_cmd.extend(["--config", args.config])

    print(f"Launching node: {' '.join(node_cmd)}")
    if args.dry_run:
        return 0
    return subprocess.call(node_cmd, cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
