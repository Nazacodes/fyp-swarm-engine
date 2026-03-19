# leader_election.py

import time
from typing import Dict, Any, Optional


class LeaderElector:
    def __init__(
        self,
        node_id: str,
        priority: float = 0.0,
        timeout: float = 10.0,
    ):
        self.node_id = node_id
        self.priority = priority
        self.timeout = timeout
        self._known_nodes: Dict[str, Dict[str, Any]] = {}  # node_id → {timestamp, prio}
        self._last_leader: Optional[str] = None

    def handle_heartbeat(self, msg: Dict[str, Any]) -> None:
        node_id = msg.get("node_id")
        if not node_id:
            return
        now = msg.get("timestamp", time.time())
        prio = msg.get("prio", 0.0)

        self._known_nodes[node_id] = {"timestamp": now, "prio": prio}

    def tick(self, now: float) -> None:
        # Remove stale nodes.
        cutoff = now - self.timeout
        self._known_nodes = {
            nid: info
            for nid, info in self._known_nodes.items()
            if info["timestamp"] > cutoff
        }

        # Do not consider self as expired here so
        # nodes can still become leader if others are gone.
        self._known_nodes[self.node_id] = {
            "timestamp": now,
            "prio": self.priority,
        }

        # Recompute leader.
        candidates = [
            (nid, info["prio"])
            for nid, info in self._known_nodes.items()
            if info["timestamp"] > cutoff
        ]
        if not candidates:
            self._last_leader = None
            return

        # Pick max‑prio; tiebreak by node_id.
        candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
        new_leader = candidates[0][0]
        self._last_leader = new_leader

    def is_leader(self) -> bool:
        return self._last_leader == self.node_id

    def current_leader(self) -> Optional[str]:
        return self._last_leader
