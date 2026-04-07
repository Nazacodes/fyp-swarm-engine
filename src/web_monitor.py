#!/usr/bin/env python
"""Web monitor for the swarm system."""

import argparse
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Tuple

from flask import Flask, redirect, render_template, request
import plotly.graph_objects as go

from config import load_config
from messaging import create_messenger

app = Flask(__name__)

# Shared state for the web UI
swarm_state: Dict[str, Dict[str, Any]] = {}
current_leader: str = None
heartbeats: Dict[str, Dict[str, Any]] = {}
messenger = None

# Runtime settings (loaded in messenger thread)
target_min_temp: float = 10.0
target_max_temp: float = 35.0
max_points: int = 300
heartbeat_stale_seconds: float = 12.0

# Data buffers
timestamps: Deque[float] = deque(maxlen=max_points)
avg_temps: Deque[float] = deque(maxlen=max_points)
temperatures: Dict[str, Deque[float]] = {}
actions: Dict[str, Deque[str]] = {}
pheromones: Dict[str, Dict[str, Deque[float]]] = {}
target_history: Deque[float] = deque(maxlen=max_points)
action_flip_window: Deque[Tuple[float, str, str]] = deque(maxlen=max_points)
last_node_action: Dict[str, str] = {}
current_target: float = 22.0


def _coerce_float(value, default: float = None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp_target(target: float) -> float:
    return max(target_min_temp, min(target_max_temp, target))


def _freshness_tag(ts: float, now: float) -> str:
    if ts is None:
        return "unknown"
    age = now - ts
    if age <= 3:
        return "fresh"
    if age <= heartbeat_stale_seconds:
        return "warning"
    return "stale"


@app.route("/set_target", methods=["POST"])
def set_target():
    global current_target

    new_target = _coerce_float(request.form.get("target_temp"))
    if new_target is None:
        return redirect("/")

    new_target = _clamp_target(new_target)
    current_target = new_target

    if messenger:
        messenger.publish("swarm.temperature.cmd.target.set", {
            "type": "target_update",
            "target_temp": new_target,
            "source": "web_portal",
            "user": "user",
            "timestamp": time.time(),
        })
    return redirect("/")


@app.route("/")
def index():
    now = time.time()
    node_views = []
    valid_temps = []
    for node_id, state in sorted(swarm_state.items()):
        temp = _coerce_float(state.get("temp"))
        ts = _coerce_float(state.get("timestamp"))
        if temp is not None:
            valid_temps.append(temp)
        node_views.append({
            "node_id": node_id,
            "temp": temp,
            "action": state.get("action", "UNKNOWN"),
            "timestamp": ts,
            "freshness": _freshness_tag(ts, now),
            "is_leader": node_id == current_leader,
        })

    avg_temp = sum(valid_temps) / len(valid_temps) if valid_temps else None
    convergence = max(0, 100 - abs((avg_temp or current_target) - current_target) * 10)
    action_flips_60s = sum(1 for ts, _, _ in action_flip_window if now - ts <= 60)

    heartbeat_views = []
    for node_id, hb in sorted(heartbeats.items()):
        ts = _coerce_float(hb.get("timestamp"))
        heartbeat_views.append({
            "node_id": node_id,
            "prio": hb.get("prio"),
            "timestamp": ts,
            "freshness": _freshness_tag(ts, now),
        })

    return render_template(
        "index.html",
        nodes=node_views,
        heartbeats=heartbeat_views,
        leader=current_leader,
        avg_temp=avg_temp,
        convergence=int(convergence),
        active_nodes=len(node_views),
        current_target=current_target,
        target_min_temp=target_min_temp,
        target_max_temp=target_max_temp,
        action_flips_60s=action_flips_60s,
    )


@app.route("/charts")
def charts():
    plots = []
    ts = list(timestamps)
    target_values = list(target_history) if target_history else [current_target] * len(ts)

    fig_temp = go.Figure()
    for node, temps in temperatures.items():
        series = list(temps)
        fig_temp.add_trace(go.Scatter(
            x=ts[-len(series):],
            y=series,
            mode="lines",
            name=node,
        ))
    if ts:
        fig_temp.add_trace(go.Scatter(
            x=ts[-len(target_values):],
            y=target_values,
            mode="lines",
            name="Target",
            line={"dash": "dash"},
        ))
    fig_temp.update_layout(
        title="Node Temperatures",
        xaxis_title="Time (epoch)",
        yaxis_title="Temp (°C)",
        yaxis={"range": [target_min_temp - 2, target_max_temp + 2]},
    )
    plots.append(fig_temp.to_json())

    action_map = {"HEAT_UP": 1, "COOL_DOWN": -1, "IDLE": 0}
    fig_action = go.Figure()
    for node, acts in actions.items():
        series = [action_map.get(a, 0) for a in acts]
        fig_action.add_trace(go.Scatter(
            x=ts[-len(series):],
            y=series,
            mode="lines",
            name=node,
        ))
    fig_action.update_layout(
        title="Actions (1 Heat, 0 Idle, -1 Cool)",
        xaxis_title="Time (epoch)",
        yaxis_title="Action State",
        yaxis={"tickvals": [-1, 0, 1], "ticktext": ["COOL", "IDLE", "HEAT"]},
    )
    plots.append(fig_action.to_json())

    fig_avg = go.Figure()
    avg_series = list(avg_temps)
    fig_avg.add_trace(go.Scatter(
        x=ts[-len(avg_series):],
        y=avg_series,
        mode="lines",
        name="Average Temp",
    ))
    if ts:
        fig_avg.add_trace(go.Scatter(
            x=ts[-len(target_values):],
            y=target_values,
            mode="lines",
            name="Target",
            line={"dash": "dash"},
        ))
    fig_avg.update_layout(
        title="Average Temperature vs Target",
        xaxis_title="Time (epoch)",
        yaxis_title="Temp (°C)",
    )
    plots.append(fig_avg.to_json())

    if pheromones:
        node = sorted(pheromones.keys())[0]
        fig_pher = go.Figure()
        for action_name, phers in pheromones[node].items():
            series = list(phers)
            fig_pher.add_trace(go.Scatter(
                x=ts[-len(series):],
                y=series,
                mode="lines",
                name=action_name,
            ))
        fig_pher.update_layout(
            title=f"Pheromones ({node})",
            xaxis_title="Time (epoch)",
            yaxis_title="Pheromone Level",
        )
        plots.append(fig_pher.to_json())

    return render_template("charts.html", plots=plots)


def message_handler(msg: dict):
    global current_leader, current_target

    topic = msg.get("topic", "")
    payload = msg.get("payload", {})
    if not isinstance(payload, dict):
        return

    now = time.time()
    msg_type = payload.get("type")

    if "telemetry/" in topic or "telemetry." in topic or msg_type in ("state", "telemetry"):
        node_id = payload.get("node_id")
        if not node_id:
            node_id = topic.split("/")[-1] if "/" in topic else topic.split(".")[-1]
        temp = _coerce_float(payload.get("temp"))
        if temp is None:
            return

        timestamps.append(now)
        target_history.append(current_target)

        if node_id not in temperatures:
            temperatures[node_id] = deque(maxlen=max_points)
            actions[node_id] = deque(maxlen=max_points)
            pheromones[node_id] = {
                "HEAT_UP": deque(maxlen=max_points),
                "COOL_DOWN": deque(maxlen=max_points),
                "IDLE": deque(maxlen=max_points),
            }

        next_action = payload.get("action", "UNKNOWN")
        prev_action = last_node_action.get(node_id)
        if prev_action and prev_action != next_action:
            action_flip_window.append((now, node_id, next_action))
        last_node_action[node_id] = next_action

        temperatures[node_id].append(temp)
        actions[node_id].append(next_action)

        node_pher = payload.get("pheromones", {})
        if isinstance(node_pher, dict) and "near" in node_pher:
            pheromones[node_id]["HEAT_UP"].append(_coerce_float(node_pher["near"].get("HEAT_UP"), 1.0))
            pheromones[node_id]["COOL_DOWN"].append(_coerce_float(node_pher["near"].get("COOL_DOWN"), 1.0))
            pheromones[node_id]["IDLE"].append(_coerce_float(node_pher["near"].get("IDLE"), 1.0))
        elif isinstance(node_pher, dict):
            for action_name in pheromones[node_id]:
                pheromones[node_id][action_name].append(_coerce_float(node_pher.get(action_name), 1.0))

        payload["temp"] = temp
        payload["timestamp"] = _coerce_float(payload.get("timestamp"), now)
        swarm_state[node_id] = payload

    elif topic == "swarm.temperature.leader":
        current_leader = payload.get("leader_id")

    elif topic == "swarm.temperature.room":
        avg_temp = _coerce_float(payload.get("avg_temp"))
        if avg_temp is not None:
            avg_temps.append(avg_temp)

    elif topic == "swarm.temperature.target":
        target = _coerce_float(payload.get("target_temp"))
        if target is not None:
            current_target = _clamp_target(target)

    elif topic == "swarm.heartbeat":
        node_id = payload.get("node_id")
        if node_id:
            heartbeats[node_id] = {
                "node_id": node_id,
                "prio": payload.get("prio", 0.0),
                "timestamp": _coerce_float(payload.get("timestamp"), now),
            }
            candidates = [(nid, hb.get("prio", 0.0)) for nid, hb in heartbeats.items()]
            if candidates:
                candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
                current_leader = candidates[0][0]


def run_messenger():
    global messenger, current_target, target_min_temp, target_max_temp, max_points
    global timestamps, avg_temps, target_history, action_flip_window
    global temperatures, actions, pheromones
    config = load_config(None)
    target_min_temp = float(config.get("target_min_temp", 10.0))
    target_max_temp = float(config.get("target_max_temp", 35.0))
    current_target = float(config.get("target_temp", 22.0))
    max_points = max(50, int(config.get("monitor_max_points", 300)))
    timestamps = deque(maxlen=max_points)
    avg_temps = deque(maxlen=max_points)
    target_history = deque(maxlen=max_points)
    action_flip_window = deque(maxlen=max_points)
    temperatures = {}
    actions = {}
    pheromones = {}

    messenger = create_messenger(config)
    messenger.subscribe([
        "swarm.temperature.telemetry.*",
        "swarm.temperature.leader",
        "swarm.temperature.room",
        "swarm.temperature.target",
        "swarm.temperature.events.#",
        "swarm.heartbeat",
    ], message_handler)

    messenger.publish("swarm.temperature.state.request", {"type": "state_request"})

    while True:
        if hasattr(messenger, "process_events"):
            messenger.process_events(time_limit=1.0)
        time.sleep(0.1)


def main():
    parser = argparse.ArgumentParser(description="Swarm web monitor")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    args = parser.parse_args()

    threading.Thread(target=run_messenger, daemon=True).start()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
