#!/usr/bin/env python
"""Quick utility to validate RabbitMQ connectivity.

This script tries to connect to RabbitMQ (using the same defaults as the project),
publishes a test message, and verifies it can be received via a subscription.

Usage:
  python test_rabbitmq.py
  python test_rabbitmq.py --host localhost --user guest --password guest
"""

import argparse
import time
import uuid
import logging

from config import load_config
from messaging import RabbitMQMessenger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s][%(levelname)s] %(message)s",
)
logger = logging.getLogger("test_rabbitmq")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test RabbitMQ connectivity and publish/subscribe")
    parser.add_argument("--host", help="RabbitMQ host")
    parser.add_argument("--user", help="RabbitMQ user")
    parser.add_argument("--password", help="RabbitMQ password")
    parser.add_argument("--exchange", default="swarm.bus", help="RabbitMQ exchange (default: swarm.bus)")
    parser.add_argument("--routing-key", default="swarm.test", help="Routing key to publish/subscribe")
    parser.add_argument("--timeout", type=float, default=5.0, help="Seconds to wait for the test message")
    args = parser.parse_args()

    # Load defaults from config/env vars
    cfg = load_config(None)

    host = args.host or cfg.get("rabbit_host")
    user = args.user or cfg.get("rabbit_user")
    password = args.password or cfg.get("rabbit_password")

    logger.info("Using RabbitMQ host=%s user=%s", host, user)

    try:
        messenger = RabbitMQMessenger(host, user, password, exchange=args.exchange)
    except Exception as e:
        logger.error("Failed to connect to RabbitMQ: %s", e)
        return 1

    received = []

    def on_message(msg):
        logger.info("Received message: %s", msg)
        received.append(msg)

    messenger.subscribe([args.routing_key], on_message)

    test_msg = {
        "type": "test",
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
    }
    logger.info("Publishing test message: %s", test_msg)
    messenger.publish(args.routing_key, test_msg)

    deadline = time.time() + args.timeout
    while time.time() < deadline and not received:
        messenger.process_events(time_limit=0.1)

    messenger.close()

    if received:
        logger.info("Success: RabbitMQ publish/subscribe works.")
        return 0

    logger.error("Timed out waiting for test message (%.1fs)", args.timeout)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
