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

from flask import Flask, render_template_string, request, redirect

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
current_target: float = 22.0
messenger = None
current_target: float = 22.0

# Data for plots
timestamps = []
temperatures: Dict[str, List[float]] = {}
actions: Dict[str, List[str]] = {}
pheromones: Dict[str, Dict[str, List[float]]] = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Swarm Temperature Control Monitor</title>
    <meta http-equiv="refresh" content="5">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .card { margin: 10px; }
        .leader { border: 3px solid #28a745; box-shadow: 0 0 10px rgba(40, 167, 69, 0.3); }
        .temp-high { color: #dc3545; }
        .temp-low { color: #007bff; }
        .temp-normal { color: #28a745; }
        .control-panel { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .control-panel h3 { margin-bottom: 15px; }
        .btn-update { background: #28a745; border: none; padding: 10px 20px; border-radius: 5px; }
        .btn-update:hover { background: #218838; }
        .stats-card { background: #f8f9fa; border-left: 4px solid #007bff; }
        .node-card { transition: transform 0.2s; }
        .node-card:hover { transform: translateY(-2px); }
    </style>
</head>
<body class="bg-light">
    <div class="container-fluid">
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
            <div class="container">
                <a class="navbar-brand" href="#"><i class="fas fa-cogs"></i> Swarm Temperature Control</a>
                <div class="navbar-nav ms-auto">
                    <a class="nav-link" href="/charts"><i class="fas fa-chart-line"></i> Charts</a>
                </div>
            </div>
        </nav>

        <div class="control-panel">
            <div class="container">
                <div class="row align-items-center">
                    <div class="col-md-6">
                        <h3><i class="fas fa-sliders-h"></i> Global Control Panel</h3>
                        <p class="mb-0">Adjust the swarm's target temperature. Changes are propagated to all nodes via the leader.</p>
                    </div>
                    <div class="col-md-6">
                        <form method="post" action="/set_target" class="d-flex align-items-center">
                            <div class="input-group me-3">
                                <span class="input-group-text"><i class="fas fa-thermometer-half"></i></span>
                                <input type="number" step="0.1" class="form-control form-control-lg" id="target_temp" name="target_temp" value="{{ "%.1f"|format(current_target) }}" required placeholder="Target °C">
                            </div>
                            <button type="submit" class="btn btn-update btn-lg">
                                <i class="fas fa-sync-alt"></i> Update Target
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-4">
                <div class="card stats-card">
                    <div class="card-body">
                        <h5 class="card-title"><i class="fas fa-chart-bar"></i> Swarm Statistics</h5>
                        <p><strong>Current Leader:</strong> {{ leader or 'None' }}</p>
                        <p><strong>Active Nodes:</strong> {{ nodes|length }}</p>
                        <p><strong>Average Temp:</strong> {{ "%.1f"|format(avg_temp) if avg_temp else 'N/A' }}°C</p>
                        <p><strong>Target Temp:</strong> {{ "%.1f"|format(current_target) }}°C</p>
                        <p><strong>Convergence:</strong> {{ convergence }}%</p>
                    </div>
                </div>
            </div>
            <div class="col-md-8">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title"><i class="fas fa-network-wired"></i> Node Status</h5>
                        <div class="row">
                            {% for node_id, state in nodes.items() %}
                            <div class="col-md-6 col-lg-4 mb-3">
                                <div class="card node-card{% if node_id == leader %} leader{% endif %}">
                                    <div class="card-body text-center">
                                        <h6 class="card-title">{{ node_id }}{% if node_id == leader %} <i class="fas fa-crown text-warning"></i>{% endif %}</h6>
                                        <p class="temp{% if state.temp > 25 %}high{% elif state.temp < 20 %}low{% else %}normal{% endif %} mb-1">
                                            <i class="fas fa-thermometer-half"></i> {{ "%.1f"|format(state.temp) }}°C
                                        </p>
                                        <p class="mb-1"><strong>{{ state.action }}</strong></p>
                                        <small class="text-muted">{{ "%.1f"|format(state.timestamp) if state.timestamp else 'N/A' }}</small>
                                    </div>
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="row mt-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title"><i class="fas fa-heartbeat"></i> Heartbeats</h5>
                        <div class="row">
                            {% for node_id, hb in heartbeats.items() %}
                            <div class="col-md-3 mb-2">
                                <div class="alert alert-info py-2 mb-0">
                                    <strong>{{ node_id }}</strong>: {{ hb.timestamp }} (prio: {{ hb.prio }})
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/set_target', methods=['POST'])
def set_target():
    new_target = float(request.form['target_temp'])
    
    # Publish to control topic
    messenger.publish("swarm.temperature.cmd.target.set", {
        "type": "target_update",
        "target_temp": new_target,
        "source": "web_portal",
        "user": "user",  # from session/auth
        "timestamp": time.time()
    })
    
    return redirect('/')

@app.route('/')
def index():
    avg_temp = sum(state['temp'] for state in swarm_state.values()) / len(swarm_state) if swarm_state else None
    target_temp = current_target
    convergence = max(0, 100 - abs(avg_temp - target_temp) * 10) if avg_temp else 0
    return render_template_string(HTML_TEMPLATE, nodes=swarm_state, leader=current_leader, heartbeats=heartbeats, avg_temp=avg_temp, convergence=int(convergence), current_target=target_temp)

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
    </script>
</body>
</html>
"""
    return render_template_string(CHARTS_TEMPLATE, plots=plots)

def message_handler(msg: dict):
    global swarm_state, current_leader, heartbeats, timestamps, temperatures, actions, pheromones, current_target
    
    topic = msg.get("topic", "")
    payload = msg.get("payload", {})
    msg_type = payload.get("type")
    
    if "telemetry/" in topic or "telemetry." in topic:
        node_id = topic.split("/")[-1] if "/" in topic else topic.split(".")[-1]
        now = time.time()
        timestamps.append(now)
        
        if node_id not in temperatures:
            temperatures[node_id] = []
            actions[node_id] = []
            pheromones[node_id] = {"HEAT_UP": [], "COOL_DOWN": [], "IDLE": []}
        
        temperatures[node_id].append(payload.get("temp", 0))
        actions[node_id].append(payload.get("action", "UNKNOWN"))
        
        # Pheromones (handle bucketed or flat)
        node_pher = payload.get("pheromones", {})
        if "near" in node_pher:
            pheromones[node_id]["HEAT_UP"].append(node_pher["near"].get("HEAT_UP", 1.0))
            pheromones[node_id]["COOL_DOWN"].append(node_pher["near"].get("COOL_DOWN", 1.0))
            pheromones[node_id]["IDLE"].append(node_pher["near"].get("IDLE", 1.0))
        else:
            for action in pheromones[node_id]:
                pheromones[node_id][action].append(node_pher.get(action, 1.0))
        
        swarm_state[node_id] = payload
        
    elif topic == "swarm.temperature.leader":
        current_leader = payload.get("leader_id")
        
    elif topic == "swarm.temperature.room":
        if "avg_temp" in payload:
            avg_temps.append(payload["avg_temp"])
            
    elif topic == "swarm.temperature.target":
        current_target = payload.get("target_temp", 22.0)
        
    elif topic == "swarm/heartbeat":
        node_id = payload.get("node_id")
        if node_id:
            heartbeats[node_id] = payload
            # Update leader
            candidates = [(nid, info["prio"]) for nid, info in heartbeats.items()]
            if candidates:
                candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
                current_leader = candidates[0][0]
        
    elif "events/" in topic or "events." in topic:
        print(f"Event: {payload}")

def run_messenger():
    global messenger
    config = load_config(None)
    messenger = create_messenger(config)
    messenger.subscribe([
        "swarm.temperature.telemetry.*",      # All node telemetry
        "swarm.temperature.leader",           # Current leader
        "swarm.temperature.room",             # Room average
        "swarm.temperature.target",           # Current target
        "swarm.temperature.events.#",         # Events like leader changes
        "swarm.heartbeat"                     # Heartbeats for priority display
    ], message_handler)

    # Request retained state on startup
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

    # Start messenger thread
    threading.Thread(target=run_messenger, daemon=True).start()

    # Run Flask app
    app.run(host=args.host, port=args.port, debug=False)

if __name__ == "__main__":
    main()
