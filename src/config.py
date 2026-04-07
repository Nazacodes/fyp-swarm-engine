# config.py

import json
import os
from typing import Dict


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def load_config(config_path: str = None) -> Dict[str, any]:
    """Load config from JSON file or env vars, with sensible defaults."""
    raw = _load_from_file(config_path) if config_path else {}

    node_id = raw.get("node_id") or os.environ.get("NODE_ID", "default")
    rabbit_host = raw.get("rabbit_host") or os.environ.get("RABBIT_HOST", "localhost")
    rabbit_user = raw.get("rabbit_user") or os.environ.get("RABBIT_USER", "guest")
    rabbit_password = raw.get("rabbit_password") or os.environ.get("RABBIT_PASSWORD", "guest")
    target_temp = _as_float(raw.get("target_temp") or os.environ.get("TARGET_TEMP", 22.0), 22.0)
    start_temp = _as_float(raw.get("start_temp") or os.environ.get("START_TEMP", 20.0), 20.0)
    has_sensor = raw.get("has_sensor", True)
    if isinstance(has_sensor, str):
        has_sensor = has_sensor.lower() in ("true", "1", "yes")

    aco_config = raw.get("aco", {})
    target_bounds = raw.get("target_bounds", {})
    return {
        "node_id": node_id,
        "rabbit_host": rabbit_host,
        "rabbit_user": rabbit_user,
        "rabbit_password": rabbit_password,
        "target_temp": target_temp,
        "start_temp": start_temp,
        "has_sensor": has_sensor,
        "target_min_temp": _as_float(
            target_bounds.get("min") or os.environ.get("TARGET_MIN_TEMP", 10.0),
            10.0,
        ),
        "target_max_temp": _as_float(
            target_bounds.get("max") or os.environ.get("TARGET_MAX_TEMP", 35.0),
            35.0,
        ),
        "peer_stale_seconds": _clamp(
            _as_float(raw.get("peer_stale_seconds") or os.environ.get("PEER_STALE_SECONDS", 10.0), 10.0),
            1.0,
            120.0,
        ),
        "aco_alpha": _as_float(aco_config.get("alpha") or os.environ.get("ACO_ALPHA", 1.6), 1.6),
        "aco_beta": _as_float(aco_config.get("beta") or os.environ.get("ACO_BETA", 1.2), 1.2),
        "aco_rho": _as_float(aco_config.get("rho") or os.environ.get("ACO_RHO", 0.92), 0.92),
        "aco_q": _as_float(aco_config.get("q") or os.environ.get("ACO_Q", 2.0), 2.0),
        "aco_deadband": _as_float(aco_config.get("deadband") or os.environ.get("ACO_DEADBAND", 0.2), 0.2),
        "aco_local_weight": _as_float(
            aco_config.get("local_weight") or os.environ.get("ACO_LOCAL_WEIGHT", 0.7),
            0.7,
        ),
        "aco_global_weight": _as_float(
            aco_config.get("global_weight") or os.environ.get("ACO_GLOBAL_WEIGHT", 0.3),
            0.3,
        ),
        "aco_history_size": int(_as_float(aco_config.get("history_size") or os.environ.get("ACO_HISTORY_SIZE", 5), 5)),
        "aco_tau0": _as_float(aco_config.get("tau0") or os.environ.get("ACO_TAU0", 1.0), 1.0),
        "aco_local_decay": _as_float(
            aco_config.get("local_decay") or os.environ.get("ACO_LOCAL_DECAY", 0.15),
            0.15,
        ),
        "aco_min_action_hold_seconds": _clamp(
            _as_float(
                aco_config.get("min_action_hold_seconds") or os.environ.get("ACO_MIN_ACTION_HOLD_SECONDS", 0.6),
                0.6,
            ),
            0.0,
            10.0,
        ),
        "monitor_max_points": int(_clamp(
            _as_float(raw.get("monitor_max_points") or os.environ.get("MONITOR_MAX_POINTS", 300), 300),
            50,
            5000,
        )),
    }


def _load_from_file(config_path: str) -> dict:
    """Load JSON config file; return empty dict if not found."""
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
