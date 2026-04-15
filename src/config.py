#!/usr/bin/env python
"""Configuration loader for swarm engine."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_CONFIG: Dict[str, Any] = {
    "node_id": "node1",
    "group_id": "zone_a",
    "messaging_mode": "rabbitmq",
    "protocol_mode": "ip",  # ip|rabbitmq|zigbee-gateway|thread-gateway|ble-gateway
    "rabbit_host": "localhost",
    "rabbit_user": "guest",
    "rabbit_password": "guest",
    "target_temp": 22.0,
    "start_temp": 20.0,
    "has_sensor": False,
    "tick_seconds": 1.0,
    "peer_stale_seconds": 8.0,
    "peer_port": 9100,
    "discovery_port": 9101,
    "discovery_interval": 2.0,
    "heartbeat_interval": 1.0,
    "ack_timeout_seconds": 0.8,
    "max_retries": 2,
    "dashboard_host": "0.0.0.0",
    "dashboard_port": 5000,
    "security": {
        "enable_auth": True,
        "enable_encryption": True,
        "psk": "swarm-local-dev-key",
        "allowed_nodes": [],
        "clock_skew_seconds": 15.0,
    },
    "aco": {
        "alpha": 1.6,
        "beta": 1.2,
        "rho": 0.92,
        "q": 2.0,
        "deadband": 0.2,
        "tau0": 1.0,
        "local_decay": 0.15,
    },
}


def _deep_merge(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(left)
    for key, value in right.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Load config from defaults + json + env vars."""
    cfg = deepcopy(DEFAULT_CONFIG)
    if config_path:
        path = Path(config_path)
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"Config at {config_path} must be an object.")
            cfg = _deep_merge(cfg, loaded)

    env_overrides: Dict[str, Any] = {}
    if os.getenv("NODE_ID"):
        env_overrides["node_id"] = os.getenv("NODE_ID")
    if os.getenv("GROUP_ID"):
        env_overrides["group_id"] = os.getenv("GROUP_ID")
    if os.getenv("MESSAGING_MODE"):
        env_overrides["messaging_mode"] = os.getenv("MESSAGING_MODE")
    if os.getenv("PROTOCOL_MODE"):
        env_overrides["protocol_mode"] = os.getenv("PROTOCOL_MODE")
    if os.getenv("RABBIT_HOST"):
        env_overrides["rabbit_host"] = os.getenv("RABBIT_HOST")
    if os.getenv("RABBIT_USER"):
        env_overrides["rabbit_user"] = os.getenv("RABBIT_USER")
    if os.getenv("RABBIT_PASSWORD"):
        env_overrides["rabbit_password"] = os.getenv("RABBIT_PASSWORD")
    if os.getenv("TARGET_TEMP"):
        env_overrides["target_temp"] = float(os.getenv("TARGET_TEMP", "22.0"))
    if os.getenv("START_TEMP"):
        env_overrides["start_temp"] = float(os.getenv("START_TEMP", "20.0"))
    if os.getenv("PEER_PORT"):
        env_overrides["peer_port"] = int(os.getenv("PEER_PORT", "9100"))
    if os.getenv("DISCOVERY_PORT"):
        env_overrides["discovery_port"] = int(os.getenv("DISCOVERY_PORT", "9101"))
    if os.getenv("TICK_SECONDS"):
        env_overrides["tick_seconds"] = float(os.getenv("TICK_SECONDS", "1.0"))
    if os.getenv("HEARTBEAT_INTERVAL"):
        env_overrides["heartbeat_interval"] = float(os.getenv("HEARTBEAT_INTERVAL", "1.0"))
    if os.getenv("PEER_STALE_SECONDS"):
        env_overrides["peer_stale_seconds"] = float(os.getenv("PEER_STALE_SECONDS", "8.0"))

    env_overrides["has_sensor"] = _bool_env("HAS_SENSOR", cfg["has_sensor"])
    cfg = _deep_merge(cfg, env_overrides)

    sec = cfg.get("security", {})
    sec["enable_auth"] = _bool_env("ENABLE_AUTH", sec.get("enable_auth", True))
    sec["enable_encryption"] = _bool_env("ENABLE_ENCRYPTION", sec.get("enable_encryption", True))
    if os.getenv("SWARM_PSK"):
        sec["psk"] = os.getenv("SWARM_PSK")
    allowed = os.getenv("ALLOWED_NODES")
    if allowed:
        sec["allowed_nodes"] = [x.strip() for x in allowed.split(",") if x.strip()]
    cfg["security"] = sec
    return cfg
