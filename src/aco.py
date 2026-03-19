# aco.py

import random
import time
from typing import List, Dict, Any, Tuple


class ACOTemperatureNode:
    def __init__(self, node_id: str, target_temp: float):
        self.node_id = node_id
        self.target_temp = target_temp
        self.actions = ["HEAT_UP", "COOL_DOWN", "IDLE"]
        self.pheromone = {action: 1.0 for action in self.actions}  # Initial pheromone
        self.evaporation_rate = 0.99  # Even slower evaporation for better learning
        self.alpha = 3.0  # Higher pheromone weight for more deterministic choices
        self.beta = 1.0   # Lower heuristic weight
        self.last_action = "IDLE"
        self.last_reward = 0.0
        self._global_avg: float = 0.0
        self._last_gather = 0.0

    def update_from_swarm(self, swarm_states: List[Dict[str, Any]]) -> None:
        """Update global average and aggregate shared pheromones."""
        temps = [s["temp"] for s in swarm_states if "temp" in s]
        if temps:
            self._global_avg = sum(temps) / len(temps)
            self._last_gather = time.time()

        # Aggregate pheromones from swarm
        swarm_pheromones = [s.get("pheromones", {}) for s in swarm_states if "pheromones" in s]
        if swarm_pheromones:
            # Average pheromones across nodes
            avg_pheromone = {}
            for action in self.actions:
                values = [p.get(action, 1.0) for p in swarm_pheromones]
                avg_pheromone[action] = sum(values) / len(values)
            # Blend with local (e.g., 70% swarm, 30% local)
            for action in self.actions:
                self.pheromone[action] = 0.7 * avg_pheromone[action] + 0.3 * self.pheromone[action]

    def get_pheromones(self) -> Dict[str, float]:
        """Return current pheromones for sharing."""
        return self.pheromone.copy()


    def _calculate_reward(self, local_temp: float, action: str) -> float:
        """Reward based on how much closer to target after action."""
        # Simulate action effect (simplified)
        if action == "HEAT_UP":
            simulated_temp = local_temp + 0.5
        elif action == "COOL_DOWN":
            simulated_temp = local_temp - 0.5
        else:
            simulated_temp = local_temp

        delta_before = abs(local_temp - self.target_temp)
        delta_after = abs(simulated_temp - self.target_temp)
        reward = max(0, delta_before - delta_after) * 10.0  # Amplify reward for stronger learning
        return reward

    def _select_action_aco(self, local_temp: float) -> str:
        """Select action using ACO probabilities."""
        probabilities = {}
        total = 0.0

        for action in self.actions:
            heuristic = self._calculate_reward(local_temp, action) + 1.0  # Avoid zero
            prob = (self.pheromone[action] ** self.alpha) * (heuristic ** self.beta)
            probabilities[action] = prob
            total += prob

        if total == 0:
            return random.choice(self.actions)

        # Roulette wheel selection
        pick = random.uniform(0, total)
        current = 0.0
        for action, prob in probabilities.items():
            current += prob
            if pick <= current:
                return action
        return self.actions[-1]  # Fallback

    def _update_pheromone(self, action: str, reward: float) -> None:
        """Update pheromone based on reward."""
        # Evaporate
        for a in self.actions:
            self.pheromone[a] *= self.evaporation_rate

        # Deposit
        self.pheromone[action] += reward

    def choose_action(self, local_temp: float, global_temp: float, is_leader: bool) -> str:
        # Use global_temp for decision making to focus on global convergence
        temp_to_use = global_temp

        # Select action via ACO
        action = self._select_action_aco(temp_to_use)

        # Calculate reward for last action (delayed update)
        if self.last_action:
            reward = self._calculate_reward(temp_to_use, self.last_action)
            self._update_pheromone(self.last_action, reward)

        self.last_action = action
        return action
