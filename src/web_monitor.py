#!/usr/bin/env python
"""Web monitor for swarm telemetry and topology."""

from __future__ import annotations

import argparse
import os
import threading
import time
from collections import deque
from typing import Deque, Dict, List

from flask import Flask, jsonify, render_template, request

from config import load_config
from messaging import create_messenger

app = Flask(__name__, template_folder="templates", static_folder="static")

STATE_LOCK = threading.Lock()
NODE_STATE: Dict[str, Dict] = {}
TIMESERIES: Deque[Dict] = deque(maxlen=1000)
TARGET_TEMP = 22.0
STALE_SECONDS = 20.0
# Keep nodes visible longer in larger swarm runs where message timing can jitter.
EVICT_SECONDS = 300.0
EXPECTED_NODE_IDS: List[str] = []
MONITOR_MESSENGER = None
MESSENGER_LOCK = threading.Lock()
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "").strip()


def _on_message(msg: Dict) -> None:
    global TARGET_TEMP
    topic = msg.get("topic", "")
    payload = msg.get("payload", {})
    now = time.time()
    if topic.startswith("swarm.temperature.telemetry."):
        node_id = payload.get("node_id")
        if not node_id:
            return
        with STATE_LOCK:
            payload["last_seen"] = now
            NODE_STATE[node_id] = payload
            TIMESERIES.append(
                {
                    "timestamp": now,
                    "node_id": node_id,
                    "temp": payload.get("temp"),
                    "target_temp": payload.get("target_temp"),
                    "action": payload.get("action"),
                }
            )
    elif topic.startswith("swarm.temperature.heartbeat."):
        node_id = payload.get("node_id")
        if not node_id:
            return
        with STATE_LOCK:
            existing = NODE_STATE.get(node_id, {})
            existing["node_id"] = node_id
            existing["group_id"] = payload.get("group_id", existing.get("group_id", "default"))
            existing["last_seen"] = now
            existing.setdefault("temp", None)
            existing.setdefault("action", "UNKNOWN")
            existing.setdefault("leader_id", existing.get("leader_id"))
            existing.setdefault("is_leader", False)
            NODE_STATE[node_id] = existing
    elif topic == "swarm.temperature.cmd.target.set":
        target = payload.get("target_temp")
        if target is not None:
            TARGET_TEMP = float(target)


def _monitor_loop(config: Dict) -> None:
    # Use a dedicated LAN peer port for monitor process to avoid collisions
    # with local node processes running on the same machine.
    config = dict(config)
    config["peer_port"] = int(config.get("monitor_peer_port", 9200))
    global MONITOR_MESSENGER
    messenger = create_messenger(config)
    with MESSENGER_LOCK:
        MONITOR_MESSENGER = messenger
    messenger.subscribe(
        ["swarm.temperature.telemetry.*", "swarm.temperature.heartbeat.*", "swarm.temperature.cmd.target.set"],
        _on_message,
    )
    while True:
        messenger.process_events(time_limit=0.2)


def _prune_evicted_nodes(now: float) -> None:
    with STATE_LOCK:
        evict = [node_id for node_id, payload in NODE_STATE.items() if (now - payload.get("last_seen", 0.0)) > EVICT_SECONDS]
        for node_id in evict:
            NODE_STATE.pop(node_id, None)


def _state_with_expected_nodes(now: float) -> Dict[str, Dict]:
    with STATE_LOCK:
        merged = dict(NODE_STATE)
    for node_id in EXPECTED_NODE_IDS:
        if node_id not in merged:
            merged[node_id] = {
                "node_id": node_id,
                "group_id": "zone_a",
                "temp": None,
                "action": "UNKNOWN",
                "last_seen": 0.0,
                "leader_id": None,
                "is_leader": False,
            }
    return merged


def _check_gateway_auth() -> bool:
    if not GATEWAY_TOKEN:
        return True
    supplied = request.headers.get("X-Gateway-Token", "")
    return supplied == GATEWAY_TOKEN


@app.route("/")
def index():
    now = time.time()
    _prune_evicted_nodes(now)
    merged = _state_with_expected_nodes(now)
    snapshot = []
    fresh_group_members: Dict[str, List[str]] = {}
    temp_by_node: Dict[str, float] = {}

    for node_id, payload in merged.items():
        age = now - payload.get("last_seen", 0.0)
        freshness = "fresh" if age <= STALE_SECONDS else "stale"
        group_id = payload.get("group_id", "default")
        temp = payload.get("temp")
        if freshness == "fresh":
            fresh_group_members.setdefault(group_id, []).append(node_id)
            if isinstance(temp, (int, float)):
                temp_by_node[node_id] = float(temp)

        snapshot.append(
            {
                "id": node_id,
                "group_id": group_id,
                "temp": temp if freshness == "fresh" else None,
                "action": payload.get("action") if freshness == "fresh" else "UNKNOWN",
                "freshness": freshness,
                "is_leader": False,
                "leader_id": None,
            }
        )

    elected_by_group: Dict[str, str] = {}
    for group_id, members in fresh_group_members.items():
        elected_by_group[group_id] = sorted(members)[0]

    for n in snapshot:
        if n["freshness"] != "fresh":
            continue
        leader_id = elected_by_group.get(n["group_id"])
        n["leader_id"] = leader_id
        n["is_leader"] = leader_id == n["id"]

    leaders = sum(1 for n in snapshot if n["is_leader"])
    fresh_count = sum(1 for n in snapshot if n["freshness"] == "fresh")
    stale_count = len(snapshot) - fresh_count
    snapshot.sort(key=lambda n: (n["freshness"] != "fresh", n["id"]))
    temps = list(temp_by_node.values())
    room_avg = round(sum(temps) / len(temps), 3) if temps else None
    room_err = round(abs(room_avg - TARGET_TEMP), 3) if room_avg is not None else None
    return render_template(
        "overview.html",
        nodes=snapshot,
        leaders=leaders,
        fresh_count=fresh_count,
        stale_count=stale_count,
        target_temp=TARGET_TEMP,
        room_avg=room_avg,
        room_err=room_err,
    )


@app.route("/charts")
def charts():
    return render_template("charts.html")


@app.route("/node-map")
def node_map():
    return render_template("node_map.html")


@app.route("/api/state")
def api_state():
    _prune_evicted_nodes(time.time())
    merged = _state_with_expected_nodes(time.time())
    return jsonify({"target_temp": TARGET_TEMP, "nodes": list(merged.values())})


@app.route("/api/timeseries")
def api_timeseries():
    with STATE_LOCK:
        # Return recent telemetry points for frontend charts.
        points = list(TIMESERIES)
    return jsonify({"points": points, "count": len(points)})


@app.route("/api/set_target", methods=["POST"])
def api_set_target():
    global TARGET_TEMP
    data = request.get_json(silent=True) or {}
    target = float(data.get("target_temp", TARGET_TEMP))
    TARGET_TEMP = target
    version = int(time.time() * 1000)
    payload = {
        "type": "target_update",
        "target_temp": target,
        "target_epoch": 1,
        "target_version": version,
        "timestamp": time.time(),
        "source": "web_monitor",
    }
    published = False
    with MESSENGER_LOCK:
        messenger = MONITOR_MESSENGER
    if messenger is not None:
        try:
            messenger.publish("swarm.temperature.cmd.target.set", payload)
            published = True
        except Exception:
            published = False
    return jsonify({"ok": True, "target_temp": target, "target_version": version, "published": published})


@app.route("/api/gateway/join", methods=["POST"])
def api_gateway_join():
    if not _check_gateway_auth():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "")).strip()
    if not node_id:
        return jsonify({"ok": False, "error": "node_id is required"}), 400
    group_id = str(data.get("group_id", "zone_a"))
    protocol_mode = str(data.get("protocol_mode", "gateway"))
    now = time.time()
    with STATE_LOCK:
        existing = NODE_STATE.get(node_id, {})
        existing["node_id"] = node_id
        existing["group_id"] = group_id
        existing["protocol_mode"] = protocol_mode
        existing["last_seen"] = now
        existing.setdefault("temp", None)
        existing.setdefault("action", "UNKNOWN")
        existing.setdefault("leader_id", None)
        existing.setdefault("is_leader", False)
        NODE_STATE[node_id] = existing
    return jsonify({"ok": True, "node_id": node_id, "group_id": group_id, "protocol_mode": protocol_mode})


@app.route("/api/gateway/heartbeat", methods=["POST"])
def api_gateway_heartbeat():
    if not _check_gateway_auth():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "")).strip()
    if not node_id:
        return jsonify({"ok": False, "error": "node_id is required"}), 400
    group_id = str(data.get("group_id", "zone_a"))
    protocol_mode = str(data.get("protocol_mode", "gateway"))
    now = time.time()
    with STATE_LOCK:
        existing = NODE_STATE.get(node_id, {})
        existing["node_id"] = node_id
        existing["group_id"] = group_id
        existing["protocol_mode"] = protocol_mode
        existing["last_seen"] = now
        existing.setdefault("temp", None)
        existing.setdefault("action", "UNKNOWN")
        existing.setdefault("leader_id", None)
        existing.setdefault("is_leader", False)
        NODE_STATE[node_id] = existing

    # Optionally mirror heartbeat onto swarm bus for observers.
    with MESSENGER_LOCK:
        messenger = MONITOR_MESSENGER
    if messenger is not None:
        try:
            messenger.publish(
                f"swarm.temperature.heartbeat.{node_id}",
                {
                    "type": "heartbeat",
                    "node_id": node_id,
                    "group_id": group_id,
                    "protocol_mode": protocol_mode,
                    "timestamp": now,
                },
            )
        except Exception:
            pass
    return jsonify({"ok": True, "node_id": node_id})


@app.route("/api/gateway/telemetry", methods=["POST"])
def api_gateway_telemetry():
    if not _check_gateway_auth():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "")).strip()
    if not node_id:
        return jsonify({"ok": False, "error": "node_id is required"}), 400
    group_id = str(data.get("group_id", "zone_a"))
    protocol_mode = str(data.get("protocol_mode", "gateway"))
    temp = data.get("temp")
    action = str(data.get("action", "IDLE"))
    target_temp = float(data.get("target_temp", TARGET_TEMP))
    now = time.time()

    payload = {
        "type": "telemetry",
        "node_id": node_id,
        "group_id": group_id,
        "protocol_mode": protocol_mode,
        "temp": temp,
        "target_temp": target_temp,
        "action": action,
        "timestamp": now,
    }
    with STATE_LOCK:
        payload["last_seen"] = now
        NODE_STATE[node_id] = payload
        TIMESERIES.append(
            {
                "timestamp": now,
                "node_id": node_id,
                "temp": temp,
                "target_temp": target_temp,
                "action": action,
            }
        )

    # Mirror to swarm bus so this gateway node participates in the same observability stream.
    with MESSENGER_LOCK:
        messenger = MONITOR_MESSENGER
    if messenger is not None:
        try:
            messenger.publish(f"swarm.temperature.telemetry.{node_id}", payload)
        except Exception:
            pass
    return jsonify({"ok": True, "node_id": node_id})


@app.route("/api/node_map")
def api_node_map():
    now = time.time()
    _prune_evicted_nodes(now)
    nodes: List[Dict] = []
    edges: List[Dict] = []
    merged = _state_with_expected_nodes(now)
    for node_id, payload in merged.items():
        age = now - payload.get("last_seen", 0.0)
        freshness = "fresh" if age <= STALE_SECONDS else "stale"
        group_id = payload.get("group_id", "default")
        nodes.append(
            {
                "id": node_id,
                "label": node_id,
                "group_id": group_id,
                "temp": payload.get("temp") if freshness == "fresh" else None,
                "action": payload.get("action") if freshness == "fresh" else "UNKNOWN",
                "freshness": freshness,
                "is_leader": False,
            }
        )

    # Elect a consistent fresh leader per group for visualization
    groups: Dict[str, List[str]] = {}
    for n in nodes:
        if n["freshness"] == "fresh":
            groups.setdefault(n["group_id"], []).append(n["id"])
    elected_by_group = {group_id: sorted(members)[0] for group_id, members in groups.items() if members}
    for n in nodes:
        if n["freshness"] == "fresh":
            n["is_leader"] = elected_by_group.get(n["group_id"]) == n["id"]

    for group_id, members in groups.items():
        if len(members) < 2:
            continue
        leader = elected_by_group[group_id]
        for member in members:
            if member == leader:
                continue
            edges.append({"id": f"{member}->{leader}", "from": member, "to": leader, "kind": "group", "group_id": group_id})

    # Leader council links: connect fresh leaders across groups (full mesh)
    fresh_leaders = sorted([leader for leader in elected_by_group.values() if leader])
    if len(fresh_leaders) > 1:
        for i in range(len(fresh_leaders)):
            for j in range(i + 1, len(fresh_leaders)):
                a = fresh_leaders[i]
                b = fresh_leaders[j]
                edges.append({"id": f"council:{a}->{b}", "from": a, "to": b, "kind": "leader_council", "group_id": "council"})
    meta = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "leader_count": len([n for n in nodes if n.get("is_leader") and n.get("freshness") == "fresh"]),
    }
    return jsonify({"nodes": nodes, "edges": edges, "meta": meta})


def main() -> int:
    parser = argparse.ArgumentParser(description="Run web monitor")
    parser.add_argument("--config", default=None)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    expected_count = int(os.getenv("EXPECTED_NODE_COUNT", "0"))
    global EXPECTED_NODE_IDS
    if expected_count > 0:
        EXPECTED_NODE_IDS = [f"node{i}" for i in range(1, expected_count + 1)]
    cfg = load_config(args.config)
    thread = threading.Thread(target=_monitor_loop, args=(cfg,), daemon=True)
    thread.start()
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
