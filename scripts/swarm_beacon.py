#!/usr/bin/env python
"""Advertise swarm connection info on local network via UDP.

Host-side utility. Broadcasts RabbitMQ/monitor connection details so edge devices
can discover and join automatically.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from typing import Dict


DISCOVERY_PORT = 5679
BROADCAST_INTERVAL = 2.0


def _local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


def run_beacon(payload: Dict, listen_port: int = DISCOVERY_PORT) -> None:
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv_sock.bind(("", listen_port))
    recv_sock.settimeout(0.5)

    running = True

    def responder() -> None:
        nonlocal running
        while running:
            try:
                data, addr = recv_sock.recvfrom(4096)
                text = data.decode("utf-8", errors="ignore").strip()
                if text == "SWARM_DISCOVERY_REQUEST":
                    recv_sock.sendto(json.dumps(payload).encode("utf-8"), addr)
            except socket.timeout:
                continue
            except Exception:
                continue

    thread = threading.Thread(target=responder, daemon=True)
    thread.start()
    print(f"Swarm beacon active on UDP {listen_port}: {payload}")
    try:
        while True:
            send_sock.sendto(json.dumps(payload).encode("utf-8"), ("255.255.255.255", listen_port))
            time.sleep(BROADCAST_INTERVAL)
    except KeyboardInterrupt:
        running = False
        print("Beacon stopped")
    finally:
        send_sock.close()
        recv_sock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Swarm host beacon")
    parser.add_argument("--swarm-name", default="fyp-swarm")
    parser.add_argument("--rabbit-host", default=None)
    parser.add_argument("--rabbit-port", type=int, default=5672)
    parser.add_argument("--monitor-port", type=int, default=5000)
    parser.add_argument("--discovery-port", type=int, default=DISCOVERY_PORT)
    args = parser.parse_args()

    host_ip = args.rabbit_host or _local_ip()
    payload = {
        "swarm_name": args.swarm_name,
        "rabbit_host": host_ip,
        "rabbit_port": args.rabbit_port,
        "monitor_port": args.monitor_port,
        "timestamp": time.time(),
    }
    run_beacon(payload, listen_port=args.discovery_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
