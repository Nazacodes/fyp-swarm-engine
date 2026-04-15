#!/usr/bin/env python
"""Simulate a non-IP gateway device joining swarm via HTTP gateway endpoints."""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.request
import urllib.error
import socket
from typing import Dict


def _post(url: str, payload: Dict, token: str = "", timeout: float = 8.0, retries: int = 4) -> Dict:
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            if token:
                req.add_header("X-Gateway-Token", token)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError) as exc:
            last_err = exc
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"POST failed after {retries} retries: {url}") from last_err


def _get_state(base_url: str, timeout: float = 8.0, retries: int = 4) -> Dict:
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(f"{base_url}/api/state", timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError) as exc:
            last_err = exc
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"GET /api/state failed after {retries} retries") from last_err


def main() -> int:
    parser = argparse.ArgumentParser(description="Gateway-join client")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--node-id", default="gateway-node1")
    parser.add_argument("--group-id", default="zone_1")
    parser.add_argument("--protocol-mode", default="zigbee-gateway")
    parser.add_argument("--start-temp", type=float, default=18.0)
    parser.add_argument("--tick-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    temp = float(args.start_temp)

    _post(
        f"{base_url}/api/gateway/join",
        {
            "node_id": args.node_id,
            "group_id": args.group_id,
            "protocol_mode": args.protocol_mode,
        },
        args.token,
        timeout=args.timeout_seconds,
        retries=args.retries,
    )
    print(f"Joined via gateway: node_id={args.node_id}, protocol={args.protocol_mode}")

    while True:
        state = _get_state(base_url, timeout=args.timeout_seconds, retries=args.retries)
        target = float(state.get("target_temp", 22.0))
        err = target - temp
        if abs(err) <= 0.2:
            action = "IDLE"
            temp += random.uniform(-0.03, 0.03)
        elif err > 0:
            action = "HEAT_UP"
            temp += min(0.18, 0.10 + random.uniform(0.0, 0.05))
        else:
            action = "COOL_DOWN"
            temp -= min(0.18, 0.10 + random.uniform(0.0, 0.05))

        try:
            _post(
                f"{base_url}/api/gateway/heartbeat",
                {
                    "node_id": args.node_id,
                    "group_id": args.group_id,
                    "protocol_mode": args.protocol_mode,
                },
                args.token,
                timeout=args.timeout_seconds,
                retries=args.retries,
            )
            _post(
                f"{base_url}/api/gateway/telemetry",
                {
                    "node_id": args.node_id,
                    "group_id": args.group_id,
                    "protocol_mode": args.protocol_mode,
                    "temp": round(temp, 3),
                    "target_temp": target,
                    "action": action,
                },
                args.token,
                timeout=args.timeout_seconds,
                retries=args.retries,
            )
        except Exception as exc:
            print(f"{args.node_id} gateway push retrying after error: {exc}")
            time.sleep(1.0)
            continue
        print(f"{args.node_id} [{args.protocol_mode}] temp={temp:.2f} target={target:.2f} action={action}")
        time.sleep(args.tick_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
