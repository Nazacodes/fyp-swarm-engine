import time
import random
from collections import deque
from typing import List, Dict, Any


class ACOTemperatureNode:
    def __init__(
        self,
        node_id: str,
        target_temp: float,
        alpha: float = 1.6,
        beta: float = 1.2,
        rho: float = 0.92,
        q: float = 2.0,
        deadband: float = 0.2,
        local_weight: float = 0.7,
        global_weight: float = 0.3,
        history_size: int = 5,
        tau0: float = 1.0,
        local_decay: float = 0.15,
        min_action_hold_seconds: float = 0.6,
    ):
        self.node_id = node_id
        self.target_temp = target_temp
        self.alpha = alpha
        self.beta = beta
        self.rho = rho
        self.q = q
        self.deadband = deadband
        self.local_weight = local_weight
        self.global_weight = global_weight
        self.history = deque(maxlen=history_size)
        self.actions = ["HEAT_UP", "COOL_DOWN", "IDLE"]
        self.tau0 = tau0
        self.local_decay = local_decay
        self.min_action_hold_seconds = max(0.0, float(min_action_hold_seconds))

        self.pheromone = {
            "far_below": {a: tau0 for a in self.actions},
            "below": {a: tau0 for a in self.actions},
            "near": {a: tau0 for a in self.actions},
            "above": {a: tau0 for a in self.actions},
            "far_above": {a: tau0 for a in self.actions},
        }

        self._global_avg = target_temp
        self._last_gather = 0.0
        self._last_action = "IDLE"
        self._last_error = None
        self._last_bucket = "near"
        self._global_target = target_temp
        self._last_action_at = 0.0

    def _bucket(self, error: float) -> str:
        if error > 1.5:
            return "far_below"
        if error > 0.35:
            return "below"
        if error < -1.5:
            return "far_above"
        if error < -0.35:
            return "above"
        return "near"

    def update_from_swarm(self, swarm_states: List[Dict[str, Any]]) -> None:
        temps = [s["temp"] for s in swarm_states if "temp" in s]
        if temps:
            self._global_avg = sum(temps) / len(temps)
            self._last_gather = time.time()

        swarm_pheromones = [s.get("pheromones", {}) for s in swarm_states if "pheromones" in s]
        if swarm_pheromones:
            for bucket in self.pheromone:
                for action in self.actions:
                    vals = []
                    for p in swarm_pheromones:
                        if bucket in p and action in p[bucket]:
                            vals.append(p[bucket][action])
                    if vals:
                        avg = sum(vals) / len(vals)
                        self.pheromone[bucket][action] = 0.85 * self.pheromone[bucket][action] + 0.15 * avg

    def set_global_target(self, new_target: float) -> None:
        """Update the global target temperature and local target setpoint."""
        self._global_target = new_target
        self.target_temp = new_target

    def get_pheromones(self) -> Dict[str, Dict[str, float]]:
        """Return current pheromone buckets."""
        return self.pheromone

    def _smooth_local(self, local_temp: float) -> float:
        self.history.append(local_temp)
        return sum(self.history) / len(self.history)

    def _heuristic(self, bucket: str, error: float) -> Dict[str, float]:
        heur = {
            "HEAT_UP": 0.2,
            "COOL_DOWN": 0.2,
            "IDLE": 0.2,
        }

        if bucket == "far_below":
            heur["HEAT_UP"] = 3.0 + abs(error)
            heur["IDLE"] = 0.3
        elif bucket == "below":
            heur["HEAT_UP"] = 2.0 + abs(error)
            heur["IDLE"] = 0.8
        elif bucket == "near":
            heur["IDLE"] = 3.0
            heur["HEAT_UP"] = 0.7
            heur["COOL_DOWN"] = 0.7
        elif bucket == "above":
            heur["COOL_DOWN"] = 2.0 + abs(error)
            heur["IDLE"] = 0.8
        elif bucket == "far_above":
            heur["COOL_DOWN"] = 3.0 + abs(error)
            heur["IDLE"] = 0.3

        return heur

    def _local_update(self, bucket: str, action: str) -> None:
        self.pheromone[bucket][action] = (
            (1 - self.local_decay) * self.pheromone[bucket][action]
            + self.local_decay * self.tau0
        )

    def _global_update(self, bucket: str, action: str, improvement: float) -> None:
        for b in self.pheromone:
            for a in self.actions:
                self.pheromone[b][a] *= self.rho

        if improvement > 0:
            self.pheromone[bucket][action] += self.q * improvement

        for b in self.pheromone:
            for a in self.actions:
                self.pheromone[b][a] = max(0.05, min(25.0, self.pheromone[b][a]))

    def _select_action(self, bucket: str, error: float) -> str:
        heur = self._heuristic(bucket, error)
        scores = {}

        for action in self.actions:
            tau = self.pheromone[bucket][action] ** self.alpha
            eta = heur[action] ** self.beta
            scores[action] = tau * eta

        total = sum(scores.values())
        if total <= 0:
            return "IDLE"

        r = random.random()
        cumulative = 0.0
        for action in self.actions:
            cumulative += scores[action] / total
            if r <= cumulative:
                return action
        return "IDLE"

    def choose_action(self, local_temp: float, global_temp: float, is_leader: bool) -> str:
        smooth_local = self._smooth_local(local_temp)

        if self._last_gather > 0:
            effective_temp = self.local_weight * smooth_local + self.global_weight * global_temp
        else:
            effective_temp = smooth_local

        current_error = self.target_temp - effective_temp
        bucket = self._bucket(current_error)

        if self._last_error is not None:
            improvement = abs(self._last_error) - abs(current_error)
            self._global_update(self._last_bucket, self._last_action, improvement)

        if abs(current_error) <= self.deadband:
            action = "IDLE"
        else:
            action = self._select_action(bucket, current_error)

        # Damp fast oscillation by holding a non-idle action briefly
        # unless the current error has crossed to the opposite side.
        now = time.time()
        if (
            self._last_action_at > 0
            and now - self._last_action_at < self.min_action_hold_seconds
            and action != self._last_action
        ):
            same_side = (
                self._last_error is None
                or current_error == 0
                or self._last_error == 0
                or (current_error > 0 and self._last_error > 0)
                or (current_error < 0 and self._last_error < 0)
            )
            if same_side:
                action = self._last_action

        self._local_update(bucket, action)

        self._last_error = current_error
        self._last_action = action
        self._last_bucket = bucket
        self._last_action_at = now
        return action
