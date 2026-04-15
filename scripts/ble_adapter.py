#!/usr/bin/env python
"""Real Bluetooth Low Energy adapter using bleak.

Discovers BLE peripherals, reads temperature data from known characteristics, and
publishes heartbeat/telemetry into the swarm over RabbitMQ using existing topics.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from bleak import BleakClient, BleakScanner
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: bleak. Install with `python -m pip install bleak`."
    ) from exc

from config import load_config  # type: ignore
from messaging import create_messenger  # type: ignore

# Common candidate temperature UUIDs (custom + standard health thermometer)
TEMP_CHAR_UUIDS = [
    "00002a1c-0000-1000-8000-00805f9b34fb",  # Temperature Measurement (Health Thermometer)
    "00002a6e-0000-1000-8000-00805f9b34fb",  # Temperature (Environmental Sensing)
]


@dataclass
class BLENode:
    node_id: str
    address: str
    group_id: str
    temp: Optional[float] = None
    action: str = "IDLE"
    last_seen: float = 0.0
    char_uuid: Optional[str] = None


class RealBLEAdapter:
    def __init__(self, config: Dict, group_id: str, scan_seconds: float = 6.0, poll_seconds: float = 2.0):
        self.cfg = dict(config)
        self.group_id = group_id
        self.scan_seconds = scan_seconds
        self.poll_seconds = poll_seconds
        self.target_temp = float(config.get("target_temp", 22.0))
        self.gateway_node_id = str(config.get("node_id", "ble-real-gateway"))
        self.protocol_mode = "ble-gateway"
        self.messenger = create_messenger(self.cfg)
        self.nodes: Dict[str, BLENode] = {}
        self.messenger.subscribe(["swarm.temperature.cmd.target.set"], self._on_target)

    def _on_target(self, msg: Dict) -> None:
        payload = msg.get("payload", {})
        target = payload.get("target_temp")
        if target is not None:
            self.target_temp = float(target)

    @staticmethod
    def _decode_temp(raw: bytes) -> Optional[float]:
        if not raw:
            return None
        # 2-byte signed integer in 0.01 C (common env-sensing format)
        if len(raw) >= 2:
            try:
                value = struct.unpack("<h", raw[:2])[0] / 100.0
                if -40.0 <= value <= 125.0:
                    return value
            except Exception:
                pass
        # fallback: 4-byte float
        if len(raw) >= 4:
            try:
                value = struct.unpack("<f", raw[:4])[0]
                if -40.0 <= value <= 125.0:
                    return value
            except Exception:
                pass
        return None

    async def _discover(self) -> None:
        found = await BleakScanner.discover(timeout=self.scan_seconds)
        for dev in found:
            node_id = f"ble-{dev.address.replace(':', '').lower()}"
            if node_id not in self.nodes:
                self.nodes[node_id] = BLENode(
                    node_id=node_id,
                    address=dev.address,
                    group_id=self.group_id,
                )

    async def _read_temp(self, node: BLENode) -> Optional[float]:
        try:
            async with BleakClient(node.address, timeout=8.0) as client:
                # Resolve characteristic once where possible.
                uuids = TEMP_CHAR_UUIDS if node.char_uuid is None else [node.char_uuid]
                for uuid in uuids:
                    try:
                        data = await client.read_gatt_char(uuid)
                        value = self._decode_temp(bytes(data))
                        if value is not None:
                            node.char_uuid = uuid
                            return value
                    except Exception:
                        continue
        except Exception:
            return None
        return None

    def _derive_action(self, temp: Optional[float]) -> str:
        if temp is None:
            return "IDLE"
        err = self.target_temp - temp
        if abs(err) <= 0.2:
            return "IDLE"
        return "HEAT_UP" if err > 0 else "COOL_DOWN"

    def _publish(self, node: BLENode) -> None:
        now = time.time()
        hb = {
            "type": "heartbeat",
            "node_id": node.node_id,
            "group_id": node.group_id,
            "protocol_mode": self.protocol_mode,
            "gateway_id": self.gateway_node_id,
            "timestamp": now,
        }
        telem = {
            "type": "telemetry",
            "node_id": node.node_id,
            "group_id": node.group_id,
            "protocol_mode": self.protocol_mode,
            "gateway_id": self.gateway_node_id,
            "temp": node.temp,
            "target_temp": self.target_temp,
            "action": node.action,
            "timestamp": now,
        }
        self.messenger.publish(f"swarm.temperature.heartbeat.{node.node_id}", hb)
        self.messenger.publish(f"swarm.temperature.telemetry.{node.node_id}", telem)

    async def run(self) -> None:
        print("BLE adapter discovering devices...")
        await self._discover()
        if not self.nodes:
            print("No BLE devices discovered. Keep running; rescans will continue.")

        while True:
            if not self.nodes:
                await self._discover()
                await asyncio.sleep(self.poll_seconds)
                continue

            for node in list(self.nodes.values()):
                temp = await self._read_temp(node)
                if temp is not None:
                    node.temp = round(temp, 3)
                    node.last_seen = time.time()
                node.action = self._derive_action(node.temp)
                self._publish(node)
                print(f"{node.node_id} addr={node.address} temp={node.temp} target={self.target_temp:.2f} action={node.action}")

            self.messenger.process_events(time_limit=0.05)
            await asyncio.sleep(self.poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Real BLE adapter for swarm")
    parser.add_argument("--config", default=None)
    parser.add_argument("--group-id", default="zone_1")
    parser.add_argument("--node-id", default="ble-real-gateway")
    parser.add_argument("--rabbit-host", default="localhost")
    parser.add_argument("--rabbit-user", default="guest")
    parser.add_argument("--rabbit-password", default="guest")
    parser.add_argument("--scan-seconds", type=float, default=6.0)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg["node_id"] = args.node_id
    cfg["group_id"] = args.group_id
    cfg["rabbit_host"] = args.rabbit_host
    cfg["rabbit_user"] = args.rabbit_user
    cfg["rabbit_password"] = args.rabbit_password
    cfg["messaging_mode"] = "rabbitmq"
    cfg["protocol_mode"] = "ble-gateway"

    adapter = RealBLEAdapter(cfg, group_id=args.group_id, scan_seconds=args.scan_seconds, poll_seconds=args.poll_seconds)
    asyncio.run(adapter.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
