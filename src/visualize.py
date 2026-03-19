#!/usr/bin/env python
"""Visualization script for swarm ACO data.

Collects data from running nodes and plots temperature, actions, and pheromone evolution.
Run this while the swarm is active to visualize learning.
"""

import time
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import threading
from typing import Dict, List, Any

from config import load_config
from messaging import create_messenger

# Data storage
timestamps = []
temperatures: Dict[str, List[float]] = {}
actions: Dict[str, List[str]] = {}
pheromones: Dict[str, Dict[str, List[float]]] = {}

def message_handler(msg: dict):
    global timestamps, temperatures, actions, pheromones
    msg_type = msg.get("type")
    if msg_type == "state":
        node_id = msg.get("node_id")
        if node_id:
            now = time.time()
            timestamps.append(now)
            if node_id not in temperatures:
                temperatures[node_id] = []
                actions[node_id] = []
                pheromones[node_id] = {action: [] for action in ["HEAT_UP", "COOL_DOWN", "IDLE"]}

            temperatures[node_id].append(msg.get("temp", 0))
            actions[node_id].append(msg.get("action", "UNKNOWN"))

            # Pheromones
            node_pher = msg.get("pheromones", {})
            for action in pheromones[node_id]:
                pheromones[node_id][action].append(node_pher.get(action, 1.0))

def run_collector():
    config = load_config(None)
    messenger = create_messenger(config)
    messenger.subscribe(["swarm.state"], message_handler)

    while True:
        if hasattr(messenger, "process_events"):
            messenger.process_events(time_limit=1.0)
        time.sleep(0.1)

def animate(frame):
    plt.clf()

    if not timestamps:
        return

    # Plot temperatures
    plt.subplot(2, 2, 1)
    for node, temps in temperatures.items():
        plt.plot(timestamps[-len(temps):], temps, label=node)
    plt.title("Node Temperatures")
    plt.xlabel("Time")
    plt.ylabel("Temp (°C)")
    plt.legend()

    # Plot actions (as numbers: HEAT=1, COOL=-1, IDLE=0)
    plt.subplot(2, 2, 2)
    action_map = {"HEAT_UP": 1, "COOL_DOWN": -1, "IDLE": 0}
    for node, acts in actions.items():
        act_nums = [action_map.get(a, 0) for a in acts]
        plt.plot(timestamps[-len(act_nums):], act_nums, label=node)
    plt.title("Actions (1=Heat, 0=Idle, -1=Cool)")
    plt.xlabel("Time")
    plt.ylabel("Action")
    plt.legend()

    # Plot pheromones for one node (e.g., first)
    if pheromones:
        node = list(pheromones.keys())[0]
        plt.subplot(2, 2, 3)
        for action, phers in pheromones[node].items():
            plt.plot(timestamps[-len(phers):], phers, label=action)
        plt.title(f"Pheromones ({node})")
        plt.xlabel("Time")
        plt.ylabel("Pheromone Level")
        plt.legend()

    plt.tight_layout()

def main():
    # Start collector thread
    threading.Thread(target=run_collector, daemon=True).start()

    # Start animation
    fig = plt.figure(figsize=(12, 8))
    ani = FuncAnimation(fig, animate, interval=2000)  # Update every 2s
    plt.show()

if __name__ == "__main__":
    main()
