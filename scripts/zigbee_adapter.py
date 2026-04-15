#!/usr/bin/env python
"""Real Zigbee adapter via Zigbee2MQTT -> swarm gateway API.

This adapter bridges physical Zigbee devices (managed by Zigbee2MQTT) into the
swarm monitor/gateway endpoints:
  - /api/gateway/join
  - /api/gateway/heartbeat
  - /api/gateway/telemetry

It also forwards swarm target updates back to Zigbee2MQTT device set topics.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, Optional

try:
    import paho.mqtt.client as mqtt
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: paho-mqtt. Install with `python -m pip install paho-mqtt`."
    ) from exc


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("zigbee_adapter")


@dataclass
class DeviceState:
    node_id: str
    group_id: str
    temp: Optional[float] = None
    action: str = "IDLE"
    last_seen: float = field(default_factory=time.time)
    joined: bool = False


class ZigbeeSwarmAdapter:
    def __init__(
        self,
        swarm_base_url: str,
        mqtt_host: str,
        mqtt_port: int,
        mqtt_topic_prefix: str,
        group_id: str,
        gateway_token: str = "",
        protocol_mode: str = "zigbee-gateway",
        heartbeat_interval: float = 2.0,
        target_push_interval: float = 4.0,
    ):
        self.swarm_base_url = swarm_base_url.rstrip("/")
        self.gateway_token = gateway_token
        self.group_id = group_id
        self.protocol_mode = protocol_mode
        self.heartbeat_interval = heartbeat_interval
        self.target_push_interval = target_push_interval
        self.topic_prefix = mqtt_topic_prefix.rstrip("/")
        self.devices: Dict[str, DeviceState] = {}
        self.current_target = 22.0
        self.last_target_push = 0.0

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(mqtt_host, mqtt_port, 60)

    def _http_post(self, path: str, payload: Dict) -> Dict:
        req = urllib.request.Request(
            f"{self.swarm_base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        if self.gateway_token:
            req.add_header("X-Gateway-Token", self.gateway_token)
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _http_get_state(self) -> Dict:
        with urllib.request.urlopen(f"{self.swarm_base_url}/api/state", timeout=10.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        logger.info("Connected to MQTT broker, subscribing to Zigbee2MQTT topics")
        client.subscribe(f"{self.topic_prefix}/+/+")
        client.subscribe(f"{self.topic_prefix}/+")

    def _normalize_device_id(self, friendly_name: str) -> str:
        return f"zigbee-{friendly_name}".replace(" ", "-")

    def _join_device(self, state: DeviceState) -> None:
        if state.joined:
            return
        self._http_post(
            "/api/gateway/join",
            {
                "node_id": state.node_id,
                "group_id": state.group_id,
                "protocol_mode": self.protocol_mode,
            },
        )
        state.joined = True
        logger.info("Joined swarm: %s", state.node_id)

    def _publish_gateway_state(self, state: DeviceState) -> None:
        self._http_post(
            "/api/gateway/heartbeat",
            {
                "node_id": state.node_id,
                "group_id": state.group_id,
                "protocol_mode": self.protocol_mode,
            },
        )
        self._http_post(
            "/api/gateway/telemetry",
            {
                "node_id": state.node_id,
                "group_id": state.group_id,
                "protocol_mode": self.protocol_mode,
                "temp": state.temp,
                "target_temp": self.current_target,
                "action": state.action,
            },
        )

    def _derive_action(self, temp: Optional[float], target: float) -> str:
        if temp is None:
            return "IDLE"
        err = target - temp
        if abs(err) <= 0.2:
            return "IDLE"
        return "HEAT_UP" if err > 0 else "COOL_DOWN"

    def _update_from_payload(self, friendly_name: str, payload: Dict) -> None:
        node_id = self._normalize_device_id(friendly_name)
        state = self.devices.get(node_id)
        if state is None:
            state = DeviceState(node_id=node_id, group_id=self.group_id)
            self.devices[node_id] = state
        if isinstance(payload.get("temperature"), (int, float)):
            state.temp = float(payload["temperature"])
        state.action = self._derive_action(state.temp, self.current_target)
        state.last_seen = time.time()
        self._join_device(state)
        self._publish_gateway_state(state)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        parts = topic.split("/")
        if len(parts) < 2:
            return
        friendly_name = parts[1]
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        if isinstance(payload, dict):
            self._update_from_payload(friendly_name, payload)

    def _push_target_to_devices(self) -> None:
        # Generic Zigbee2MQTT set payload. Device-specific converters may vary.
        payload = json.dumps({"target_temp": self.current_target})
        for state in self.devices.values():
            friendly = state.node_id.replace("zigbee-", "", 1)
            self.client.publish(f"{self.topic_prefix}/{friendly}/set", payload)

    def run(self) -> None:
        self.client.loop_start()
        try:
            while True:
                now = time.time()
                try:
                    state = self._http_get_state()
                    self.current_target = float(state.get("target_temp", self.current_target))
                except Exception as exc:
                    logger.warning("Failed to fetch swarm state: %s", exc)

                for st in self.devices.values():
                    if now - st.last_seen <= self.heartbeat_interval * 3:
                        try:
                            self._publish_gateway_state(st)
                        except Exception as exc:
                            logger.warning("Failed to publish gateway state for %s: %s", st.node_id, exc)

                if now - self.last_target_push >= self.target_push_interval:
                    self._push_target_to_devices()
                    self.last_target_push = now

                time.sleep(self.heartbeat_interval)
        finally:
            self.client.loop_stop()
            self.client.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(description="Real Zigbee to swarm adapter")
    parser.add_argument("--swarm-host", default="localhost")
    parser.add_argument("--swarm-port", type=int, default=5000)
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-topic-prefix", default="zigbee2mqtt")
    parser.add_argument("--group-id", default="zone_1")
    parser.add_argument("--protocol-mode", default="zigbee-gateway")
    parser.add_argument("--gateway-token", default="")
    parser.add_argument("--heartbeat-interval", type=float, default=2.0)
    parser.add_argument("--target-push-interval", type=float, default=4.0)
    args = parser.parse_args()

    adapter = ZigbeeSwarmAdapter(
        swarm_base_url=f"http://{args.swarm_host}:{args.swarm_port}",
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_topic_prefix=args.mqtt_topic_prefix,
        group_id=args.group_id,
        gateway_token=args.gateway_token,
        protocol_mode=args.protocol_mode,
        heartbeat_interval=args.heartbeat_interval,
        target_push_interval=args.target_push_interval,
    )
    adapter.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
