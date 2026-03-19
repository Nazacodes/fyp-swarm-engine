# node.py

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

        # Set priority; for now use node_id as lexicographic tie‑breaker.
        self.priority = float(
            "".join(
                f"{ord(c)/100:.3f}" for c in self.node_id
            ).replace(".", "")
        ) / 10**9

        # Components.
        self.messenger: SwarmMessenger = create_messenger(config)
        self.temperature_source: TemperatureSource = (
            RealSensorSource(self.node_id)
            if config["has_sensor"]
            else MockTemperatureSource()
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

        # Local cache of swarm state: node_id → last state.
        self.swarm_state: Dict[str, dict] = {}

    def _publish_state(self, local_temp: float, is_leader: bool, action: str) -> None:
        pheromones = self.aco.get_pheromones() if hasattr(self.aco, 'get_pheromones') else {}
        state = {
            "type": "state",
            "node_id": self.node_id,
            "temp": local_temp,
            "action": action,
            "is_leader": is_leader,
            "pheromones": pheromones,
        }
        self.messenger.publish("swarm.state", state)

    def _publish_heartbeat(self, now: float) -> None:
        hb = {
            "type": "heartbeat",
            "node_id": self.node_id,
            "timestamp": now,
            "prio": self.priority,
        }
        self.messenger.publish("swarm.heartbeat", hb)

    def _on_message(self, msg: dict) -> None:
        msg_type = msg.get("type")
        if not msg_type:
            return

        if msg_type == "heartbeat":
            self.leader_elector.handle_heartbeat(msg)
        elif msg_type == "state":
            node_id = msg.get("node_id")
            if node_id:
                self.swarm_state[node_id] = msg

    def run(self, interval: float = 0.2) -> None:
        # Subscribe to messages.
        self.messenger.subscribe(
            routing_keys=["swarm.heartbeat", "swarm.state"],
            on_message=self._on_message,
        )

        # Run a small internal loop; no separate threads.
        last_tick = time.time()
        while True:
            now = time.time()

            # Tick leader election.
            if now - last_tick >= 1.0:
                self.leader_elector.tick(now)
                last_tick = now

            # Read local temperature.
            try:
                local_temp = self.temperature_source.read()
            except Exception as e:
                logger.warning("Sensor read failed; using fallback temp 22.0: %r", e)
                local_temp = 22.0

            # Compute global average if we have swarm state.
            global_avg = sum(s['temp'] for s in self.swarm_state.values()) / len(self.swarm_state) if self.swarm_state else local_temp

            # Ask ACO what to do.
            is_leader = self.leader_elector.is_leader()
            action = self.aco.choose_action(local_temp=local_temp, global_temp=global_avg, is_leader=is_leader)

            # Apply action to temperature source if possible.
            if hasattr(self.temperature_source, 'apply_action'):
                self.temperature_source.apply_action(action)

            # Re-read temperature after action applied.
            try:
                local_temp = self.temperature_source.read()
            except Exception as e:
                logger.warning("Sensor read failed after action; using fallback temp 22.0: %r", e)
                local_temp = 22.0

            # Update ACO with swarm state if leader.
            if is_leader:
                self.aco.update_from_swarm(list(self.swarm_state.values()))

            # Publish state.
            self._publish_state(
                local_temp=local_temp,
                is_leader=is_leader,
                action=action,
            )

            # Publish heartbeat.
            self._publish_heartbeat(now)

            # Log only if leader changed.
            leader = self.leader_elector.current_leader()
            if leader == self.node_id:
                logger.info("Leader: %s (temp=%.1f, action=%s)", self.node_id, local_temp, action)
            elif leader:
                logger.debug("Leader: %s (temp=%.1f, action=%s)", self.node_id, local_temp, action)

            # Process any pending messaging events (RabbitMQ non-blocking).
            if hasattr(self.messenger, "process_events"):
                try:
                    self.messenger.process_events(time_limit=0)
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
