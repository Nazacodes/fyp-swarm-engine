# config.py

import json
import os
from typing import Dict


def load_config(config_path: str = None) -> Dict[str, any]:
    """Load config from JSON file or env vars, with sensible defaults."""
    raw = _load_from_file(config_path) if config_path else {}

    node_id = raw.get("node_id") or os.environ.get("NODE_ID", "default")
    rabbit_host = raw.get("rabbit_host") or os.environ.get("RABBIT_HOST", "localhost")
    rabbit_user = raw.get("rabbit_user") or os.environ.get("RABBIT_USER", "guest")
    rabbit_password = raw.get("rabbit_password") or os.environ.get("RABBIT_PASSWORD", "guest")
    target_temp = float(raw.get("target_temp") or os.environ.get("TARGET_TEMP", 22.0))
    has_sensor = raw.get("has_sensor", True)
    if isinstance(has_sensor, str):
        has_sensor = has_sensor.lower() in ("true", "1", "yes")

    return {
        "node_id": node_id,
        "rabbit_host": rabbit_host,
        "rabbit_user": rabbit_user,
        "rabbit_password": rabbit_password,
        "target_temp": target_temp,
        "has_sensor": has_sensor,
    }


def _load_from_file(config_path: str) -> dict:
    """Load JSON config file; return empty dict if not found."""
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
