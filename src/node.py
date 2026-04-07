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
            alpha=config.get("aco_alpha", 1.6),
            beta=config.get("aco_beta", 1.2),
            rho=config.get("aco_rho", 0.92),
            q=config.get("aco_q", 2.0),
            deadband=config.get("aco_deadband", 0.2),
            local_weight=config.get("aco_local_weight", 0.7),
            global_weight=config.get("aco_global_weight", 0.3),
            history_size=config.get("aco_history_size", 5),
            tau0=config.get("aco_tau0", 1.0),
            local_decay=config.get("aco_local_decay", 0.15),
            min_action_hold_seconds=config.get("aco_min_action_hold_seconds", 0.6),
        )

        self.swarm_state: Dict[str, dict] = {}
        self.target_min_temp = float(config.get("target_min_temp", 10.0))
        self.target_max_temp = float(config.get("target_max_temp", 35.0))
        self.peer_stale_seconds = float(config.get("peer_stale_seconds", 10.0))

    def _coerce_float(self, value, default: float = None):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _clamp_target(self, target: float) -> float:
        return max(self.target_min_temp, min(self.target_max_temp, target))

    def _fresh_peer_states(self, now: float) -> List[dict]:
        fresh = []
        for state in self.swarm_state.values():
            ts = self._coerce_float(state.get("timestamp"))
            temp = self._coerce_float(state.get("temp"))
            if temp is None:
                continue
            if ts is None or now - ts <= self.peer_stale_seconds:
                fresh.append(state)
        return fresh

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
        if not isinstance(msg, dict):
            return

        if "topic" in msg:
            topic = msg["topic"]
            payload = msg.get("payload", {})
        else:
            topic = None
            payload = msg

        if not isinstance(payload, dict):
            return

        msg_type = payload.get("type")
        if not msg_type:
            return

        if msg_type == "heartbeat":
            self.leader_elector.handle_heartbeat(payload)
        elif msg_type in ("state", "telemetry"):
            node_id = payload.get("node_id")
            temp = self._coerce_float(payload.get("temp"))
            if node_id and node_id != self.node_id and temp is not None:  # Store peers only
                payload["temp"] = temp
                ts = self._coerce_float(payload.get("timestamp"), time.time())
                payload["timestamp"] = ts if ts is not None else time.time()
                self.swarm_state[node_id] = payload
        elif msg_type == "target_update":
            new_target = self._coerce_float(payload.get("target_temp"))
            if new_target is not None:
                new_target = self._clamp_target(new_target)
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

            fresh_states = self._fresh_peer_states(now)

            # Compute global average (include self + fresh peers only)
            all_temps = [self._coerce_float(s.get("temp"), local_temp) for s in fresh_states] + [local_temp]
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
                all_states = fresh_states + [{
                    "temp": local_temp, "pheromones": getattr(self.aco, "get_pheromones", lambda: {})()
                }]
                self.aco.update_from_swarm(all_states)

            # Publish everything
            self._publish_state(local_temp, is_leader, action)
            self._publish_heartbeat(now)

            leader_id = self.leader_elector.current_leader()
            if leader_id == self.node_id:
                logger.info("Leader %s: %.1f°C %s (peers: %d)", self.node_id, local_temp, action, len(fresh_states))
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
