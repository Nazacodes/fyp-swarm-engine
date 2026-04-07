import argparse
import json
import logging
import time
import sys
from typing import Dict, List

from config import load_config
from messaging import SwarmMessenger, create_messenger
from sensor_input import TemperatureSource, RealSensorSource, MockTemperatureSource
from leader_election import LeaderElector
from aco import ACOTemperatureNode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s][%(levelname)s] %(message)s",
)
logger = logging.getLogger("node")


class Node:
    def __init__(self, config: Dict[str, any]):
        self.config = config
        self.node_id = config["node_id"]

        # Priority from node_id
        self.priority = float(
            "".join(f"{ord(c)/100:.3f}" for c in self.node_id).replace(".", "")
        ) / 10**9

        # Components
        self.messenger: SwarmMessenger = create_messenger(config)
        if config["has_sensor"]:
            self.temperature_source = RealSensorSource(self.node_id)
        else:
            self.temperature_source = MockTemperatureSource(
                start_temp=config["start_temp"],
                target_temp=config["target_temp"],
            )
        self.leader_elector = LeaderElector(
            node_id=self.node_id,
            priority=self.priority,
            timeout=10.0,
        )
        self.aco = ACOTemperatureNode(
            node_id=self.node_id,
            target_temp=config["target_temp"],
        )

        self.swarm_state: Dict[str, dict] = {}

    def _publish_state(self, local_temp: float, is_leader: bool, action: str) -> None:
        # Safe attribute access
        global_target = getattr(self.aco, "_global_target", self.aco.target_temp)
        pheromones = getattr(self.aco, "get_pheromones", lambda: {})()

        state = {
            "type": "state",  # Backward compatible for graphs
            "node_id": self.node_id,
            "temp": local_temp,
            "action": action,
            "is_leader": is_leader,
            "global_temp": getattr(self.aco, "_global_avg", local_temp),
            "global_target_temp": global_target,
            "local_target_temp": self.aco.target_temp,
            "pheromones": pheromones,
            "timestamp": time.time()
        }

        # DOT-separated RabbitMQ topic keys
        self.messenger.publish(f"swarm.temperature.telemetry.{self.node_id}", state)

        if is_leader:
            self.messenger.publish("swarm.temperature.leader", {
                "leader_id": self.node_id,
                "timestamp": time.time()
            })

            self.messenger.publish("swarm.temperature.room", {
                "avg_temp": getattr(self.aco, "_global_avg", local_temp),
                "target_temp": global_target,
                "node_count": len(self.swarm_state),
                "timestamp": time.time()
            })

            self.messenger.publish("swarm.temperature.target", {
                "target_temp": global_target,
                "timestamp": time.time()
            })

    def _publish_heartbeat(self, now: float) -> None:
        self.messenger.publish("swarm.heartbeat", {
            "type": "heartbeat",
            "node_id": self.node_id,
            "timestamp": now,
            "prio": self.priority,
        })

    def _on_message(self, msg: dict) -> None:
        if "topic" in msg:
            topic = msg["topic"]
            payload = msg["payload"]
        else:
            topic = None
            payload = msg

        msg_type = payload.get("type")
        if not msg_type:
            return

        if msg_type == "heartbeat":
            self.leader_elector.handle_heartbeat(payload)
        elif msg_type in ("state", "telemetry"):
            node_id = payload.get("node_id")
            if node_id and node_id != self.node_id:  # Store peers only
                self.swarm_state[node_id] = payload
        elif msg_type == "target_update":
            new_target = payload.get("target_temp")
            if new_target is not None:
                if hasattr(self.aco, "set_global_target"):
                    self.aco.set_global_target(new_target)
                logger.info(f"[{self.node_id}] Target update: {new_target}°C")

    def run(self, interval: float = 0.2) -> None:
        # DOT-separated RabbitMQ topic subscriptions
        self.messenger.subscribe([
            "swarm.heartbeat",
            "swarm.temperature.telemetry.*",      # All peer telemetry
            "swarm.temperature.leader",
            "swarm.temperature.room",
            "swarm.temperature.target",
            "swarm.temperature.cmd.target.set",
            "swarm.temperature.events.#"
        ], self._on_message)

        last_tick = time.time()
        while True:
            now = time.time()

            if now - last_tick >= 1.0:
                self.leader_elector.tick(now)
                last_tick = now

            # Read sensor
            try:
                local_temp = self.temperature_source.read()
            except Exception as e:
                logger.warning("Sensor read failed: %r", e)
                local_temp = 22.0

            # Compute global average (include self)
            all_temps = [s["temp"] for s in self.swarm_state.values()] + [local_temp]
            global_avg = sum(all_temps) / len(all_temps) if all_temps else local_temp

            is_leader = self.leader_elector.is_leader()

            # ACO decision
            action = self.aco.choose_action(
                local_temp=local_temp,
                global_temp=global_avg,
                is_leader=is_leader,
            )

            # Apply action (simulation only)
            if hasattr(self.temperature_source, 'apply_action'):
                self.temperature_source.apply_action(action)

            # Leader updates ACO from swarm
            if is_leader:
                all_states = list(self.swarm_state.values()) + [{
                    "temp": local_temp, "pheromones": getattr(self.aco, "get_pheromones", lambda: {})()
                }]
                self.aco.update_from_swarm(all_states)

            # Publish everything
            self._publish_state(local_temp, is_leader, action)
            self._publish_heartbeat(now)

            leader_id = self.leader_elector.current_leader()
            if leader_id == self.node_id:
                logger.info("Leader %s: %.1f°C %s (peers: %d)", self.node_id, local_temp, action, len(self.swarm_state))
            elif leader_id:
                logger.debug("Node %s: %.1f°C %s (leader: %s)", self.node_id, local_temp, action, leader_id)

            # Process events
            if hasattr(self.messenger, "process_events"):
                try:
                    self.messenger.process_events(time_limit=0.01)
                except Exception:
                    pass

            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="JSON config file", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    node = Node(config)

    try:
        node.run()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        node.messenger.close()


if __name__ == "__main__":
    main()
