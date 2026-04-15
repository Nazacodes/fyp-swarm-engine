#!/usr/bin/env python
"""Protocol-agnostic message model and adapter contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Protocol


@dataclass
class NormalizedMessage:
    topic: str
    payload: Dict[str, Any]
    sender_id: str = ""
    timestamp: float = 0.0
    protocol: str = "ip"
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProtocolAdapter(Protocol):
    """Common contract for protocol adapters/gateways."""

    protocol_name: str

    def subscribe(self, patterns: Iterable[str], callback: Callable[[Dict[str, Any]], None]) -> None:
        ...

    def publish(self, topic: str, payload: Dict[str, Any], include_self: bool = False) -> None:
        ...

    def process_events(self, time_limit: float = 0.1) -> None:
        ...

    def close(self) -> None:
        ...


class GatewayRegistry:
    """Tracks logical device mappings behind non-IP protocol gateways."""

    def __init__(self):
        self._logical_devices: Dict[str, Dict[str, Any]] = {}

    def register(self, logical_device_id: str, protocol: str, attrs: Dict[str, Any] | None = None) -> None:
        self._logical_devices[logical_device_id] = {
            "protocol": protocol,
            "attrs": attrs or {},
        }

    def all_devices(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._logical_devices)
