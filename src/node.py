#!/usr/bin/env python
"""Swarm node runtime with ACO decisions and LAN failure handling."""

from __future__ import annotations

import argparse
import logging
import random
import signal
import threading
import time
from typing import Dict, Optional

from aco import ACOTemperatureController
from config import load_config
from messaging import LanMessenger, create_messenger

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s][%(levelname)s] %(message)s")
logger = logging.getLogger("node")


class SwarmNode:
    def __init__(self, config: Dict):
        self.config = config
        self.node_id = config["node_id"]
        self.group_id = config.get("group_id", "default")
        self.protocol_mode = str(config.get("protocol_mode", "ip"))
        self.target_temp = float(config.get("target_temp", 22.0))
        self.current_temp = float(config.get("start_temp", 20.0))
        self.tick_seconds = float(config.get("tick_seconds", 1.0))
        self.peer_stale_seconds = float(config.get("peer_stale_seconds", 8.0))
        self.running = True
        self.last_action = "IDLE"
        self.is_leader = False
        self.target_epoch = int(config.get("target_epoch", 1))
        self.target_version = int(config.get("target_version_start", 0))
        self.metrics = {
            "sent_count": 0,
            "recv_count": 0,
            "retry_count": 0,
            "last_recovery_seconds": 0.0,
            "convergence_error": 0.0,
        }

        aco_cfg = config.get("aco", {})
        self.aco = ACOTemperatureController(
            alpha=float(aco_cfg.get("alpha", 1.6)),
            beta=float(aco_cfg.get("beta", 1.2)),
            rho=float(aco_cfg.get("rho", 0.92)),
            q=float(aco_cfg.get("q", 2.0)),
            deadband=float(aco_cfg.get("deadband", 0.2)),
            tau0=float(aco_cfg.get("tau0", 1.0)),
            local_decay=float(aco_cfg.get("local_decay", 0.15)),
        )
        self.messenger = create_messenger(config)
        self.peer_state: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.max_step_per_tick = 0.18
        self.outlier_pull = 0.18
        self.messenger.subscribe(
            [
                "swarm.temperature.telemetry.*",
                "swarm.temperature.heartbeat.*",
                "swarm.temperature.cmd.target.set",
                "swarm.temperature.leader.sync",
                "swarm.temperature.group.target.*",
            ],
            self.on_message,
        )

    def _reconnect_messenger(self) -> None:
        try:
            self.messenger.close()
        except Exception:
            pass
        self.messenger = create_messenger(self.config)
        self.messenger.subscribe(
            [
                "swarm.temperature.telemetry.*",
                "swarm.temperature.heartbeat.*",
                "swarm.temperature.cmd.target.set",
                "swarm.temperature.leader.sync",
                "swarm.temperature.group.target.*",
            ],
            self.on_message,
        )

    def _is_newer_target(self, epoch: int, version: int) -> bool:
        return (epoch, version) > (self.target_epoch, self.target_version)

    def _next_target_version(self) -> int:
        self.target_version += 1
        return self.target_version

    def _broadcast_group_target(self) -> None:
        payload = {
            "type": "group_target_apply",
            "node_id": self.node_id,
            "group_id": self.group_id,
            "target_temp": self.target_temp,
            "target_epoch": self.target_epoch,
            "target_version": self.target_version,
            "timestamp": time.time(),
        }
        self.messenger.publish(f"swarm.temperature.group.target.{self.group_id}", payload)
        self.metrics["sent_count"] += 1

    def _broadcast_leader_sync(self) -> None:
        payload = {
            "type": "leader_target_sync",
            "node_id": self.node_id,
            "group_id": self.group_id,
            "target_temp": self.target_temp,
            "target_epoch": self.target_epoch,
            "target_version": self.target_version,
            "timestamp": time.time(),
        }
        self.messenger.publish("swarm.temperature.leader.sync", payload)
        self.metrics["sent_count"] += 1

    def _broadcast_leader_presence(self) -> None:
        payload = {
            "type": "leader_presence",
            "node_id": self.node_id,
            "group_id": self.group_id,
            "target_temp": self.target_temp,
            "target_epoch": self.target_epoch,
            "target_version": self.target_version,
            "timestamp": time.time(),
        }
        self.messenger.publish("swarm.temperature.leader.sync", payload)
        self.metrics["sent_count"] += 1

    def _apply_target(self, target: float, epoch: int, version: int) -> None:
        self.target_temp = float(target)
        self.target_epoch = int(epoch)
        self.target_version = int(version)

    def on_message(self, msg: Dict) -> None:
        topic = msg.get("topic", "")
        payload = msg.get("payload", {})
        sender = payload.get("node_id") or msg.get("sender_id")
        if sender and sender != self.node_id:
            self.metrics["recv_count"] += 1
            with self.lock:
                self.peer_state[sender] = {"payload": payload, "last_seen": time.time()}
        if topic == "swarm.temperature.cmd.target.set":
            # Apply monitor-issued target updates on every node immediately.
            # Leaders also fan the update out for cross-group consistency.
            target = payload.get("target_temp")
            if target is None:
                return
            incoming_epoch = int(payload.get("target_epoch", self.target_epoch))
            incoming_version = int(payload.get("target_version", 0))
            if incoming_version <= 0:
                incoming_version = self._next_target_version()
            if self._is_newer_target(incoming_epoch, incoming_version):
                self._apply_target(float(target), incoming_epoch, incoming_version)
                if self.is_leader:
                    self._broadcast_leader_sync()
                    self._broadcast_group_target()
            return

        if topic == "swarm.temperature.leader.sync":
            msg_type = payload.get("type")
            if msg_type != "leader_target_sync":
                # Presence/heartbeat sync keeps council connectivity visible but does not mutate targets.
                return
            if not self.is_leader:
                return
            if sender == self.node_id:
                return
            target = payload.get("target_temp")
            if target is None:
                return
            incoming_epoch = int(payload.get("target_epoch", self.target_epoch))
            incoming_version = int(payload.get("target_version", 0))
            if self._is_newer_target(incoming_epoch, incoming_version):
                self._apply_target(float(target), incoming_epoch, incoming_version)
                self._broadcast_group_target()
            return

        if topic.startswith("swarm.temperature.group.target."):
            target_group = payload.get("group_id")
            if target_group != self.group_id:
                return
            target = payload.get("target_temp")
            if target is None:
                return
            incoming_epoch = int(payload.get("target_epoch", self.target_epoch))
            incoming_version = int(payload.get("target_version", 0))
            if self._is_newer_target(incoming_epoch, incoming_version):
                self._apply_target(float(target), incoming_epoch, incoming_version)

    def _simulate_temp(self, action: str) -> None:
        drift = random.uniform(-0.06, 0.06)
        delta = 0.0
        if action == "HEAT_UP":
            delta = 0.22 + drift
        elif action == "COOL_DOWN":
            delta = -0.22 + drift
        else:
            delta = drift

        # Rate-limit actuator effect to reduce overshoot spikes.
        delta = max(-self.max_step_per_tick, min(self.max_step_per_tick, delta))
        self.current_temp += delta

    def _fresh_peers(self) -> Dict[str, Dict]:
        now = time.time()
        fresh = {}
        with self.lock:
            for node_id, state in self.peer_state.items():
                age = now - state["last_seen"]
                if age <= self.peer_stale_seconds:
                    fresh[node_id] = state["payload"]
        return fresh

    def _compute_leader(self, fresh: Dict[str, Dict]) -> str:
        """Elect one leader per group using deterministic lowest node_id."""
        candidates = [self.node_id]
        for peer_id, payload in fresh.items():
            if payload.get("group_id", self.group_id) == self.group_id:
                candidates.append(peer_id)
        return sorted(set(candidates))[0]

    def _publish_heartbeat(self) -> None:
        payload = {
            "type": "heartbeat",
            "node_id": self.node_id,
            "group_id": self.group_id,
            "protocol_mode": self.protocol_mode,
            "timestamp": time.time(),
        }
        self.messenger.publish(f"swarm.temperature.heartbeat.{self.node_id}", payload)
        self.metrics["sent_count"] += 1

    def _publish_state(self, probs: Dict[str, float]) -> None:
        fresh = self._fresh_peers()
        leader_id = self._compute_leader(fresh)
        self.is_leader = leader_id == self.node_id
        avg_temp = self.current_temp
        if fresh:
            peer_temps = [float(p.get("temp", self.current_temp)) for p in fresh.values()]
            avg_temp = (self.current_temp + sum(peer_temps)) / (len(peer_temps) + 1)

        # Outlier damping: if this node is far from room average, nudge it toward consensus.
        divergence = self.current_temp - avg_temp
        if abs(divergence) > 1.2:
            self.current_temp -= divergence * self.outlier_pull
            avg_temp = (self.current_temp + sum(float(p.get("temp", self.current_temp)) for p in fresh.values())) / (
                (len(fresh) + 1) if fresh else 1
            )
        self.metrics["convergence_error"] = round(abs(avg_temp - self.target_temp), 4)

        payload = {
            "type": "telemetry",
            "node_id": self.node_id,
            "group_id": self.group_id,
            "protocol_mode": self.protocol_mode,
            "leader_id": leader_id,
            "is_leader": self.is_leader,
            "temp": round(self.current_temp, 3),
            "target_temp": self.target_temp,
            "target_epoch": self.target_epoch,
            "target_version": self.target_version,
            "avg_temp": round(avg_temp, 3),
            "action": self.last_action,
            "pheromones": {"near": self.aco.pheromone},
            "peer_count": len(fresh),
            "room_divergence": round(abs(self.current_temp - avg_temp), 4),
            "timestamp": time.time(),
            "metrics": self.metrics,
        }
        self.messenger.publish(f"swarm.temperature.telemetry.{self.node_id}", payload, include_self=True)
        self.metrics["sent_count"] += 1

        if self.is_leader:
            self.messenger.publish(
                f"swarm.temperature.leader.{self.group_id}",
                {
                    "type": "leader_heartbeat",
                    "node_id": self.node_id,
                    "group_id": self.group_id,
                    "timestamp": time.time(),
                },
            )
            self.metrics["sent_count"] += 1
            self._broadcast_leader_presence()

    def run(self) -> None:
        logger.info("Node %s started (group=%s)", self.node_id, self.group_id)
        last_heartbeat = 0.0
        while self.running:
            try:
                start = time.time()
                action, probs = self.aco.choose_action(self.current_temp, self.target_temp)
                self.last_action = action
                self._simulate_temp(action)
                self._publish_state(probs)
                if time.time() - last_heartbeat >= float(self.config.get("heartbeat_interval", 1.0)):
                    self._publish_heartbeat()
                    last_heartbeat = time.time()
                self.messenger.process_events(time_limit=0.05)
                elapsed = time.time() - start
                sleep_time = max(0.01, self.tick_seconds - elapsed)
                time.sleep(sleep_time)
            except Exception:
                logger.exception("Node %s loop error; reconnecting messenger", self.node_id)
                time.sleep(0.5)
                self._reconnect_messenger()

    def stop(self) -> None:
        self.running = False
        self.messenger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run swarm node")
    parser.add_argument("--config", type=str, default=None, help="Path to config json")
    args = parser.parse_args()
    cfg = load_config(args.config)
    node = SwarmNode(cfg)

    def _stop(*_):
        logger.info("Stopping node %s", node.node_id)
        node.stop()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        node.run()
    except Exception:
        logger.exception("Node %s crashed with unhandled exception", node.node_id)
        raise
    finally:
        node.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
