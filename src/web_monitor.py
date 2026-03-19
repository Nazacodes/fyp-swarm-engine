#!/usr/bin/env python
"""Web monitor for the swarm system.

Runs a simple Flask web server that displays real-time swarm state.
Subscribes to RabbitMQ messages and updates a shared state.

Usage:
  python web_monitor.py [--host 0.0.0.0] [--port 5000]
"""

import argparse
import json
import threading
import time
from typing import Dict, Any, List

from flask import Flask, render_template_string

import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder

from config import load_config
from messaging import create_messenger

app = Flask(__name__)

# Shared state for the web UI
swarm_state: Dict[str, Dict[str, Any]] = {}
current_leader: str = None
heartbeats: Dict[str, Dict[str, Any]] = {}
avg_temps: List[float] = []

# Data for plots
timestamps = []
temperatures: Dict[str, List[float]] = {}
actions: Dict[str, List[str]] = {}
pheromones: Dict[str, Dict[str, List[float]]] = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Swarm Monitor</title>
    <meta http-equiv="refresh" content="1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .card { margin: 10px; }
        .leader { border: 2px solid green; }
        .temp-high { color: red; }
        .temp-low { color: blue; }
        .temp-normal { color: green; }
    </style>
</head>
<body class="bg-light">
    <div class="container">
        <h1 class="mt-4">Swarm Temperature Control Monitor</h1>
        <a href="/charts" class="btn btn-primary mb-3">View Interactive Charts</a>
        <div class="row">
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Swarm Stats</h5>
                        <p>Current Leader: <strong>{{ leader or 'None' }}</strong></p>
                        <p>Active Nodes: <strong>{{ nodes|length }}</strong></p>
                        <p>Average Temp: <strong>{{ "%.1f"|format(avg_temp) if avg_temp else 'N/A' }}°C</strong></p>
                        <p>Convergence: <strong>{{ convergence }}%</strong></p>
                    </div>
                </div>
            </div>
        </div>
        <h2>Nodes</h2>
        <div class="row">
            {% for node_id, state in nodes.items() %}
            <div class="col-md-3">
                <div class="card{% if node_id == leader %} leader{% endif %}">
                    <div class="card-body">
                        <h5 class="card-title">{{ node_id }}</h5>
                        <p class="card-text temp{% if state.temp > 25 %}high{% elif state.temp < 20 %}low{% else %}normal{% endif %}">
                            Temp: <strong>{{ "%.1f"|format(state.temp) }}°C</strong>
                        </p>
                        <p>Action: <strong>{{ state.action }}</strong></p>
                        <p>Is Leader: {{ state.is_leader }}</p>
                        <small>Last Update: {{ state.timestamp }}</small>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        <h2>Heartbeats</h2>
        <ul class="list-group">
            {% for node_id, hb in heartbeats.items() %}
            <li class="list-group-item">{{ node_id }}: {{ hb.timestamp }} (prio: {{ hb.prio }})</li>
            {% endfor %}
        </ul>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    avg_temp = sum(state['temp'] for state in swarm_state.values()) / len(swarm_state) if swarm_state else None
    target_temp = 22.0
    convergence = max(0, 100 - abs(avg_temp - target_temp) * 10) if avg_temp else 0
    return render_template_string(HTML_TEMPLATE, nodes=swarm_state, leader=current_leader, heartbeats=heartbeats, avg_temp=avg_temp, convergence=int(convergence))

@app.route('/charts')
def charts():
    # Create plots
    plots = []

    # Temperature plot
    fig_temp = go.Figure()
    for node, temps in temperatures.items():
        fig_temp.add_trace(go.Scatter(x=timestamps[-len(temps):], y=temps, mode='lines', name=node))
    fig_temp.update_layout(title='Node Temperatures', xaxis_title='Time', yaxis_title='Temp (°C)', yaxis=dict(range=[10, 40]))
    plots.append(fig_temp.to_json())

    # Actions plot (as numbers)
    action_map = {"HEAT_UP": 1, "COOL_DOWN": -1, "IDLE": 0}
    fig_action = go.Figure()
    for node, acts in actions.items():
        act_nums = [action_map.get(a, 0) for a in acts]
        fig_action.add_trace(go.Scatter(x=timestamps[-len(act_nums):], y=act_nums, mode='lines', name=node))
    fig_action.update_layout(title='Actions (1=Heat, 0=Idle, -1=Cool)', xaxis_title='Time', yaxis_title='Action')
    plots.append(fig_action.to_json())

    # Average temperature plot
    fig_avg = go.Figure()
    fig_avg.add_trace(go.Scatter(x=timestamps[-len(avg_temps):], y=avg_temps, mode='lines', name='Average Temp'))
    fig_avg.update_layout(title='Average Temperature', xaxis_title='Time', yaxis_title='Temp (°C)', yaxis=dict(range=[10, 40]))
    plots.append(fig_avg.to_json())

    # Pheromones plot for first node
    if pheromones:
        node = list(pheromones.keys())[0]
        fig_pher = go.Figure()
        for action, phers in pheromones[node].items():
            fig_pher.add_trace(go.Scatter(x=timestamps[-len(phers):], y=phers, mode='lines', name=action))
        fig_pher.update_layout(title=f'Pheromones ({node})', xaxis_title='Time', yaxis_title='Pheromone Level')
        plots.append(fig_pher.to_json())

    CHARTS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Swarm Charts</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <meta http-equiv="refresh" content="2">
</head>
<body>
    <h1>Swarm ACO Charts</h1>
    <a href="/">Back to Monitor</a>
    <div id="temp-plot"></div>
    <div id="action-plot"></div>
    <div id="avg-plot"></div>
    <div id="pher-plot"></div>
    <script>
        var plots = {{ plots | safe }};
        Plotly.newPlot('temp-plot', JSON.parse(plots[0]).data, JSON.parse(plots[0]).layout);
        Plotly.newPlot('action-plot', JSON.parse(plots[1]).data, JSON.parse(plots[1]).layout);
        Plotly.newPlot('avg-plot', JSON.parse(plots[2]).data, JSON.parse(plots[2]).layout);
        if (plots.length > 3) {
            Plotly.newPlot('pher-plot', JSON.parse(plots[3]).data, JSON.parse(plots[3]).layout);
        }
        if (plots[2]) Plotly.newPlot('pher-plot', JSON.parse(plots[2]).data, JSON.parse(plots[2]).layout);
    </script>
</body>
</html>
"""
    return render_template_string(CHARTS_TEMPLATE, plots=plots)

def message_handler(msg: dict):
    global swarm_state, current_leader, heartbeats, timestamps, temperatures, actions, pheromones
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

            swarm_state[node_id] = msg
            # Update average temp
            if swarm_state:
                avg = sum(s['temp'] for s in swarm_state.values()) / len(swarm_state)
                avg_temps.append(avg)
    elif msg_type == "heartbeat":
        node_id = msg.get("node_id")
        if node_id:
            heartbeats[node_id] = msg
            # Update leader
            candidates = [(nid, info["prio"]) for nid, info in heartbeats.items()]
            if candidates:
                candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
                current_leader = candidates[0][0]

def run_messenger():
    config = load_config(None)
    messenger = create_messenger(config)
    messenger.subscribe(["swarm.state", "swarm.heartbeat"], message_handler)

    while True:
        if hasattr(messenger, "process_events"):
            messenger.process_events(time_limit=1.0)
        time.sleep(0.1)

def main():
    parser = argparse.ArgumentParser(description="Swarm web monitor")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    args = parser.parse_args()

    # Start messenger thread
    threading.Thread(target=run_messenger, daemon=True).start()

    # Run Flask app
    app.run(host=args.host, port=args.port, debug=False)

if __name__ == "__main__":
    main()
