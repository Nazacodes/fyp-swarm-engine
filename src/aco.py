#!/usr/bin/env python
"""ACO routines used by swarm nodes and routing experiments."""

from __future__ import annotations

import random
from typing import Dict, List, Tuple


ACTIONS = ("HEAT_UP", "COOL_DOWN", "IDLE")


class ACOTemperatureController:
    def __init__(self, alpha: float, beta: float, rho: float, q: float, deadband: float, tau0: float, local_decay: float):
        self.alpha = alpha
        self.beta = beta
        self.rho = rho
        self.q = q
        self.deadband = deadband
        self.local_decay = local_decay
        self.pheromone: Dict[str, float] = {action: tau0 for action in ACTIONS}
        self.min_tau = 0.05
        self.max_tau = 8.0

    def _heuristic(self, error: float) -> Dict[str, float]:
        if abs(error) <= self.deadband:
            return {"HEAT_UP": 0.2, "COOL_DOWN": 0.2, "IDLE": 1.0}
        if error > 0:
            return {"HEAT_UP": 1.0, "COOL_DOWN": 0.1, "IDLE": 0.25}
        return {"HEAT_UP": 0.1, "COOL_DOWN": 1.0, "IDLE": 0.25}

    def choose_action(self, current_temp: float, target_temp: float) -> Tuple[str, Dict[str, float]]:
        error = target_temp - current_temp
        # Deterministic guard rails near and far from target improve stability.
        if abs(error) <= self.deadband:
            self._local_update("IDLE")
            return "IDLE", {"HEAT_UP": 0.05, "COOL_DOWN": 0.05, "IDLE": 0.90}
        if error >= 1.0:
            self._local_update("HEAT_UP")
            return "HEAT_UP", {"HEAT_UP": 0.85, "COOL_DOWN": 0.05, "IDLE": 0.10}
        if error <= -1.0:
            self._local_update("COOL_DOWN")
            return "COOL_DOWN", {"HEAT_UP": 0.05, "COOL_DOWN": 0.85, "IDLE": 0.10}

        heuristics = self._heuristic(error)
        weights: Dict[str, float] = {}
        for action in ACTIONS:
            tau = max(self.pheromone[action], 1e-6) ** self.alpha
            eta = max(heuristics[action], 1e-6) ** self.beta
            weights[action] = tau * eta
        total = sum(weights.values())
        probs = {k: (v / total if total else 1.0 / len(ACTIONS)) for k, v in weights.items()}

        pick = random.random()
        cumulative = 0.0
        choice = "IDLE"
        for action in ACTIONS:
            cumulative += probs[action]
            if pick <= cumulative:
                choice = action
                break
        self._local_update(choice)
        return choice, probs

    def _local_update(self, action: str) -> None:
        for key in ACTIONS:
            self.pheromone[key] *= (1.0 - self.local_decay)
        self.pheromone[action] += self.q * 0.1
        self._clamp_pheromone()

    def global_update(self, reward_by_action: Dict[str, float]) -> None:
        for action in ACTIONS:
            self.pheromone[action] = self.rho * self.pheromone[action] + reward_by_action.get(action, 0.0)
        self._clamp_pheromone()

    def _clamp_pheromone(self) -> None:
        for action in ACTIONS:
            self.pheromone[action] = min(self.max_tau, max(self.min_tau, self.pheromone[action]))


class ACORouter:
    """Simple ACO next-hop selector for impaired links."""

    def __init__(self, alpha: float = 1.5, beta: float = 2.0, rho: float = 0.85, q: float = 1.0):
        self.alpha = alpha
        self.beta = beta
        self.rho = rho
        self.q = q
        self.pheromone: Dict[Tuple[str, str], float] = {}

    def choose_next_hop(self, current: str, candidates: List[str], link_cost: Dict[Tuple[str, str], float]) -> str:
        if not candidates:
            return current
        weights = []
        for candidate in candidates:
            edge = (current, candidate)
            tau = self.pheromone.get(edge, 1.0) ** self.alpha
            eta = (1.0 / max(link_cost.get(edge, 1.0), 1e-6)) ** self.beta
            weights.append((candidate, tau * eta))
        total = sum(weight for _, weight in weights)
        if total <= 0:
            return random.choice(candidates)
        pick = random.random()
        cumulative = 0.0
        for candidate, weight in weights:
            cumulative += weight / total
            if pick <= cumulative:
                return candidate
        return weights[-1][0]

    def reinforce_path(self, path: List[Tuple[str, str]], path_cost: float) -> None:
        if not path:
            return
        deposit = self.q / max(path_cost, 1e-6)
        for edge in list(self.pheromone.keys()):
            self.pheromone[edge] *= self.rho
        for edge in path:
            self.pheromone[edge] = self.pheromone.get(edge, 1.0) + deposit
