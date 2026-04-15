#!/usr/bin/env python
"""Bluetooth-style gateway adapter over RabbitMQ.

This script simulates BLE peripherals joining the swarm while using your existing
RabbitMQ queue transport. It publishes standard swarm heartbeat/telemetry topics
with `protocol_mode=ble-gateway`, so it appears as a protocol-agnostic member.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_config  # type: ignore
from messaging import create_messenger  # type: ignore


@dataclass
class BLEDeviceState:
    node_id: str
    group_id: str
    temp: float
    action: str = "IDLE"


class BluetoothGatewayAdapter:
    def __init__(self, config: Dict, device_count: int, start_temp: float):
        self.config = dict(config)
        self.node_id = str(config.get("node_id", "ble-gateway"))
        self.group_id = str(config.get("group_id", "zone_1"))
        self.target_temp = float(config.get("target_temp", 22.0))
        self.tick_seconds = float(config.get("tick_seconds", 1.0))
        self.protocol_mode = "ble-gateway"
        self.messenger = create_messenger(self.config)
        self.devices: Dict[str, BLEDeviceState] = {}
        for i in range(1, device_count + 1):
            device_node = f"ble-node{i}"
            t = start_temp + random.uniform(-2.5, 2.5)
            self.devices[device_node] = BLEDeviceState(node_id=device_node, group_id=self.group_id, temp=t)

        self.messenger.subscribe(["swarm.temperature.cmd.target.set"], self._on_message)

    def _on_message(self, msg: Dict) -> None:
        payload = msg.get("payload", {})
        target = payload.get("target_temp")
        if target is not None:
            self.target_temp = float(target)

    def _step_action(self, temp: float) -> str:
        err = self.target_temp - temp
        if abs(err) <= 0.2:
            return "IDLE"
        return "HEAT_UP" if err > 0 else "COOL_DOWN"

    def _step_temp(self, state: BLEDeviceState) -> None:
        drift = random.uniform(-0.03, 0.03)
        if state.action == "HEAT_UP":
            state.temp += 0.12 + drift
        elif state.action == "COOL_DOWN":
            state.temp -= 0.12 + drift
        else:
            state.temp += drift
        state.temp = max(0.0, min(40.0, state.temp))

    def _publish_device(self, state: BLEDeviceState) -> None:
        now = time.time()
        heartbeat = {
            "type": "heartbeat",
            "node_id": state.node_id,
            "group_id": state.group_id,
            "protocol_mode": self.protocol_mode,
            "gateway_id": self.node_id,
            "timestamp": now,
        }
        telemetry = {
            "type": "telemetry",
            "node_id": state.node_id,
            "group_id": state.group_id,
            "protocol_mode": self.protocol_mode,
            "gateway_id": self.node_id,
            "temp": round(state.temp, 3),
            "target_temp": self.target_temp,
            "action": state.action,
            "timestamp": now,
        }
        self.messenger.publish(f"swarm.temperature.heartbeat.{state.node_id}", heartbeat)
        self.messenger.publish(f"swarm.temperature.telemetry.{state.node_id}", telemetry)

    def run(self) -> None:
        print(f"Bluetooth gateway '{self.node_id}' active with {len(self.devices)} BLE devices")
        print(f"Using RabbitMQ host={self.config.get('rabbit_host')} group={self.group_id}")
        while True:
            start = time.time()
            for state in self.devices.values():
                state.action = self._step_action(state.temp)
                self._step_temp(state)
                self._publish_device(state)
            self.messenger.process_events(time_limit=0.05)
            elapsed = time.time() - start
            time.sleep(max(0.05, self.tick_seconds - elapsed))


def main() -> int:
    parser = argparse.ArgumentParser(description="Bluetooth adapter using RabbitMQ transport")
    parser.add_argument("--config", default=None, help="Optional config json")
    parser.add_argument("--node-id", default="ble-gateway")
    parser.add_argument("--group-id", default="zone_1")
    parser.add_argument("--rabbit-host", default="localhost")
    parser.add_argument("--rabbit-user", default="guest")
    parser.add_argument("--rabbit-password", default="guest")
    parser.add_argument("--devices", type=int, default=2, help="Number of BLE logical devices")
    parser.add_argument("--start-temp", type=float, default=20.0)
    parser.add_argument("--tick-seconds", type=float, default=1.0)
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg["node_id"] = args.node_id
    cfg["group_id"] = args.group_id
    cfg["rabbit_host"] = args.rabbit_host
    cfg["rabbit_user"] = args.rabbit_user
    cfg["rabbit_password"] = args.rabbit_password
    cfg["messaging_mode"] = "rabbitmq"
    cfg["protocol_mode"] = "ble-gateway"
    cfg["tick_seconds"] = args.tick_seconds

    adapter = BluetoothGatewayAdapter(cfg, device_count=args.devices, start_temp=args.start_temp)
    adapter.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
