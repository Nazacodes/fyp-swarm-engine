#!/usr/bin/env python
"""Messaging backends: LAN transport and RabbitMQ."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from security import MessageSecurity
from protocol_agnostic import GatewayRegistry

try:
    import pika
except Exception:  # pragma: no cover - optional dependency runtime guard
    pika = None


logger = logging.getLogger("messaging")
GATEWAYS = GatewayRegistry()


def _topic_match(pattern: str, topic: str) -> bool:
    p_parts = pattern.split(".")
    t_parts = topic.split(".")
    i = 0
    j = 0
    while i < len(p_parts) and j < len(t_parts):
        if p_parts[i] == "#":
            return True
        if p_parts[i] == "*":
            i += 1
            j += 1
            continue
        if p_parts[i] != t_parts[j]:
            return False
        i += 1
        j += 1
    if i == len(p_parts) and j == len(t_parts):
        return True
    return i < len(p_parts) and p_parts[i] == "#"


class LanMessenger:
    """UDP discovery + TCP message transport with ack/retry."""

    def __init__(self, config: Dict[str, Any]):
        self.node_id = config["node_id"]
        self.peer_port = int(config.get("peer_port", 9100))
        self.discovery_port = int(config.get("discovery_port", 9101))
        self.discovery_interval = float(config.get("discovery_interval", 2.0))
        configured_allowed = config.get("security", {}).get("allowed_nodes", [])
        self.allowed_nodes = set(configured_allowed) if configured_allowed else set()

        sec_cfg = config.get("security", {})
        self.security = MessageSecurity(
            node_id=self.node_id,
            psk=sec_cfg.get("psk", "swarm-local-dev-key"),
            clock_skew_seconds=float(sec_cfg.get("clock_skew_seconds", 15.0)),
        )
        self.enable_auth = bool(sec_cfg.get("enable_auth", True))
        self.enable_encryption = bool(sec_cfg.get("enable_encryption", True))
        self.ack_timeout = float(config.get("ack_timeout_seconds", 0.8))
        self.max_retries = int(config.get("max_retries", 2))

        self._subscriptions: List[Tuple[List[str], Callable[[Dict[str, Any]], None]]] = []
        self._pending_ack: Dict[str, bool] = {}
        self._peers: Dict[str, Tuple[str, int, float]] = {}
        self._running = True
        self._seq = 0
        self._lock = threading.Lock()

        self._tcp_server_thread = threading.Thread(target=self._run_tcp_server, daemon=True)
        self._udp_discovery_thread = threading.Thread(target=self._run_discovery, daemon=True)
        self._tcp_server_thread.start()
        self._udp_discovery_thread.start()

    def peers_snapshot(self) -> Dict[str, Tuple[str, int, float]]:
        with self._lock:
            return dict(self._peers)

    def subscribe(self, patterns: Iterable[str], callback: Callable[[Dict[str, Any]], None]) -> None:
        self._subscriptions.append((list(patterns), callback))

    def publish(self, topic: str, payload: Dict[str, Any], include_self: bool = False) -> None:
        self._seq += 1
        plain_payload = payload
        envelope = {
            "topic": topic,
            "sender_id": self.node_id,
            "seq": self._seq,
            "timestamp": time.time(),
            "msg_id": str(uuid.uuid4()),
        }
        if self.enable_encryption:
            envelope["payload_enc"] = self.security.encrypt_payload(plain_payload)
        else:
            envelope["payload"] = plain_payload
        if self.enable_auth:
            envelope["signature"] = self.security.sign(envelope)

        if include_self:
            self._dispatch_message(topic, plain_payload, self.node_id, envelope["seq"], envelope["timestamp"], envelope["msg_id"])

        peers = self.peers_snapshot()
        for peer_id, (host, port, _) in peers.items():
            if peer_id == self.node_id:
                continue
            self._send_with_retry(host, port, envelope)

    def process_events(self, time_limit: float = 0.1) -> None:
        time.sleep(time_limit)

    def close(self) -> None:
        self._running = False

    def _run_discovery(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        recv.bind(("", self.discovery_port))
        recv.settimeout(0.5)

        while self._running:
            announce = {
                "node_id": self.node_id,
                "peer_port": self.peer_port,
                "timestamp": time.time(),
            }
            try:
                sock.sendto(json.dumps(announce).encode("utf-8"), ("255.255.255.255", self.discovery_port))
                data, addr = recv.recvfrom(2048)
                payload = json.loads(data.decode("utf-8"))
                peer_id = payload.get("node_id")
                peer_port = int(payload.get("peer_port", self.peer_port))
                if not peer_id or peer_id == self.node_id:
                    continue
                if self.allowed_nodes and peer_id not in self.allowed_nodes:
                    continue
                with self._lock:
                    self._peers[peer_id] = (addr[0], peer_port, time.time())
            except socket.timeout:
                pass
            except Exception as exc:  # pragma: no cover
                logger.debug("discovery error: %s", exc)
            time.sleep(self.discovery_interval)

    def _run_tcp_server(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("", self.peer_port))
        srv.listen(8)
        srv.settimeout(0.5)
        while self._running:
            try:
                conn, addr = srv.accept()
                threading.Thread(target=self._handle_conn, args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as exc:  # pragma: no cover
                logger.debug("tcp accept error: %s", exc)

    def _handle_conn(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        with conn:
            raw = conn.recv(65535)
            if not raw:
                return
            try:
                envelope = json.loads(raw.decode("utf-8"))
                if envelope.get("topic") == "__ack__":
                    self._pending_ack[envelope.get("msg_id", "")] = True
                    return
                if self.enable_auth and not self.security.verify(envelope):
                    return
                sender_id = envelope.get("sender_id", "")
                if self.allowed_nodes and sender_id not in self.allowed_nodes:
                    return
                seq = int(envelope.get("seq", 0))
                ts = float(envelope.get("timestamp", 0.0))
                if not self.security.validate_freshness_and_replay(sender_id, seq, ts):
                    return

                if "payload_enc" in envelope:
                    payload = self.security.safe_decrypt(envelope["payload_enc"])
                else:
                    payload = envelope.get("payload", {})
                topic = envelope.get("topic", "")
                msg_id = envelope.get("msg_id", "")
                self._dispatch_message(topic, payload, sender_id, seq, ts, msg_id)

                ack = {"topic": "__ack__", "msg_id": msg_id, "sender_id": self.node_id}
                conn.sendall(json.dumps(ack).encode("utf-8"))
                with self._lock:
                    # Keep discovered sender port from UDP discovery.
                    # Do not overwrite with local peer_port (that breaks routing).
                    existing = self._peers.get(sender_id)
                    if existing:
                        self._peers[sender_id] = (existing[0], existing[1], time.time())
                    else:
                        self._peers[sender_id] = (addr[0], self.peer_port, time.time())
            except Exception as exc:  # pragma: no cover
                logger.debug("tcp handler error: %s", exc)

    def _send_with_retry(self, host: str, port: int, envelope: Dict[str, Any]) -> None:
        msg_id = envelope["msg_id"]
        for _ in range(self.max_retries + 1):
            self._pending_ack[msg_id] = False
            try:
                with socket.create_connection((host, port), timeout=self.ack_timeout) as conn:
                    conn.sendall(json.dumps(envelope).encode("utf-8"))
                    conn.settimeout(self.ack_timeout)
                    raw = conn.recv(4096)
                    if raw:
                        ack = json.loads(raw.decode("utf-8"))
                        if ack.get("topic") == "__ack__" and ack.get("msg_id") == msg_id:
                            self._pending_ack[msg_id] = True
                            return
            except Exception:
                pass
            if self._pending_ack.get(msg_id):
                return

    def _dispatch_message(self, topic: str, payload: Dict[str, Any], sender_id: str, seq: int, timestamp: float, msg_id: str) -> None:
        msg = {
            "topic": topic,
            "payload": payload,
            "sender_id": sender_id,
            "seq": seq,
            "timestamp": timestamp,
            "msg_id": msg_id,
        }
        for patterns, callback in self._subscriptions:
            if any(_topic_match(pattern, topic) for pattern in patterns):
                callback(msg)


class RabbitMQMessenger:
    """Existing rabbitmq mode retained for compatibility."""

    def __init__(self, host: str, user: str, password: str, exchange: str = "swarm.bus"):
        if pika is None:
            raise RuntimeError("pika not installed; install requirements.txt")
        self.host = host
        self.user = user
        self.password = password
        self.exchange = exchange
        self.conn = None
        self.channel = None
        self.queue_name = ""
        self.callbacks: List[Tuple[List[str], Callable[[Dict[str, Any]], None]]] = []
        self._lock = threading.Lock()
        self._connect()

    def _connect(self) -> None:
        creds = pika.PlainCredentials(self.user, self.password)
        params = pika.ConnectionParameters(host=self.host, credentials=creds, heartbeat=30)
        self.conn = pika.BlockingConnection(params)
        self.channel = self.conn.channel()
        self.channel.exchange_declare(exchange=self.exchange, exchange_type="topic", durable=False)
        result = self.channel.queue_declare(queue="", exclusive=True)
        self.queue_name = result.method.queue
        # Re-bind existing subscriptions on reconnect
        for patterns, callback in self.callbacks:
            self._bind_consumer(patterns, callback)

    def _ensure_connection(self) -> None:
        if self.conn is None or self.channel is None or self.conn.is_closed:
            self._connect()

    def subscribe(self, patterns: Iterable[str], callback: Callable[[Dict[str, Any]], None]) -> None:
        patterns_list = list(patterns)
        self.callbacks.append((patterns_list, callback))
        with self._lock:
            self._ensure_connection()
            self._bind_consumer(patterns_list, callback)

    def _bind_consumer(self, patterns_list: List[str], callback: Callable[[Dict[str, Any]], None]) -> None:
        for pattern in patterns_list:
            self.channel.queue_bind(exchange=self.exchange, queue=self.queue_name, routing_key=pattern)

        def _on_message(ch, method, props, body):
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                payload = {}
            message = {"topic": method.routing_key, "payload": payload}
            callback(message)

        self.channel.basic_consume(queue=self.queue_name, on_message_callback=_on_message, auto_ack=True)

    def publish(self, topic: str, payload: Dict[str, Any], include_self: bool = False) -> None:
        body = json.dumps(payload).encode("utf-8")
        for _ in range(3):
            try:
                with self._lock:
                    self._ensure_connection()
                    self.channel.basic_publish(exchange=self.exchange, routing_key=topic, body=body)
                return
            except Exception as exc:
                logger.warning("rabbit publish retry due to error: %s", exc)
                time.sleep(0.2)
                with self._lock:
                    try:
                        if self.conn and not self.conn.is_closed:
                            self.conn.close()
                    except Exception:
                        pass
                    self.conn = None
                    self.channel = None

    def process_events(self, time_limit: float = 0.1) -> None:
        try:
            with self._lock:
                self._ensure_connection()
                self.conn.process_data_events(time_limit=time_limit)
        except Exception as exc:
            logger.warning("rabbit process_events reconnect due to error: %s", exc)
            with self._lock:
                try:
                    if self.conn and not self.conn.is_closed:
                        self.conn.close()
                except Exception:
                    pass
                self.conn = None
                self.channel = None
            time.sleep(min(0.5, time_limit))

    def close(self) -> None:
        try:
            if self.conn and not self.conn.is_closed:
                self.conn.close()
        except Exception:
            pass


class InMemoryMessenger:
    def __init__(self):
        self.subs: List[Tuple[List[str], Callable[[Dict[str, Any]], None]]] = []

    def subscribe(self, patterns: Iterable[str], callback: Callable[[Dict[str, Any]], None]) -> None:
        self.subs.append((list(patterns), callback))

    def publish(self, topic: str, payload: Dict[str, Any], include_self: bool = False) -> None:
        msg = {"topic": topic, "payload": payload}
        for patterns, callback in self.subs:
            if any(_topic_match(p, topic) for p in patterns):
                callback(msg)

    def process_events(self, time_limit: float = 0.1) -> None:
        time.sleep(time_limit)

    def close(self) -> None:
        return


def create_messenger(config: Dict[str, Any]):
    mode = str(config.get("messaging_mode", "lan")).lower()
    protocol_mode = str(config.get("protocol_mode", "ip")).lower()

    # Protocol aliases route through existing adapters while preserving a protocol tag.
    if protocol_mode in {"zigbee-gateway", "thread-gateway", "ble-gateway"}:
        logical_id = str(config.get("node_id", "unknown"))
        GATEWAYS.register(logical_id, protocol_mode)
        config = dict(config)
        config["messaging_mode"] = "rabbitmq" if mode != "memory" else "memory"
        mode = str(config["messaging_mode"]).lower()

    if mode == "rabbitmq":
        return RabbitMQMessenger(
            config.get("rabbit_host", "localhost"),
            config.get("rabbit_user", "guest"),
            config.get("rabbit_password", "guest"),
        )
    if mode == "memory":
        return InMemoryMessenger()
    return LanMessenger(config)
