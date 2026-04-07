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
avg_temps: List[float] = []
swarm_state: Dict[str, dict] = {}

def message_handler(msg: dict):
    global timestamps, temperatures, actions, pheromones, avg_temps, swarm_state

    topic = msg.get("topic", "")
    payload = msg.get("payload", {})
    msg_type = payload.get("type")

    if "telemetry." in topic and msg_type in ("state", "telemetry"):
        node_id = payload.get("node_id")
        if node_id:
            now = time.time()
            timestamps.append(now)
            if node_id not in temperatures:
                temperatures[node_id] = []
                actions[node_id] = []
                pheromones[node_id] = {action: [] for action in ["HEAT_UP", "COOL_DOWN", "IDLE"]}

            temperatures[node_id].append(payload.get("temp", 0))
            actions[node_id].append(payload.get("action", "UNKNOWN"))
            swarm_state[node_id] = payload

            # Pheromones
            node_pher = payload.get("pheromones", {})
            if isinstance(node_pher, dict) and "near" in node_pher:  # Handle bucketed pheromones
                bucket_pher = node_pher["near"]
                for action in pheromones[node_id]:
                    pheromones[node_id][action].append(bucket_pher.get(action, 1.0))
            else:
                # Fallback for old flat structure
                for action in pheromones[node_id]:
                    pheromones[node_id][action].append(node_pher.get(action, 1.0))

            if swarm_state:
                avg = sum(state["temp"] for state in swarm_state.values()) / len(swarm_state)
                avg_temps.append(avg)

def run_collector():
    config = load_config(None)
    messenger = create_messenger(config)
    messenger.subscribe(["swarm.temperature.telemetry.*"], message_handler)

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

    # Plot room average temperature
    plt.subplot(2, 2, 3)
    if avg_temps:
        plt.plot(timestamps[-len(avg_temps):], avg_temps, color='black', linewidth=2.5, label='Room Avg')
        plt.axhline(y=22.0, color='red', linestyle='--', linewidth=1.5, label='Target')
    plt.title('Room Average Temperature')
    plt.xlabel('Time')
    plt.ylabel('Temp (°C)')
    plt.legend()

    # Plot pheromones for one node (e.g., first)
    if pheromones:
        node = list(pheromones.keys())[0]
        plt.subplot(2, 2, 4)
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
