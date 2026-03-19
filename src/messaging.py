# messaging.py

import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Callable, List

import pika


logger = logging.getLogger(__name__)


class SwarmMessenger(ABC):
    @abstractmethod
    def publish(self, routing_key: str, payload: dict) -> None:
        ...

    @abstractmethod
    def subscribe(self, routing_keys: List[str], on_message: Callable[[Dict], None]) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


class RabbitMQMessenger(SwarmMessenger):
    def __init__(self, host: str, user: str, password: str, exchange: str = "swarm.bus"):
        self.exchange = exchange
        self.host = host
        self.user = user
        self.password = password
        self.connection = None
        self.channel = None
        self.queue_name = None
        self._connect()

    def _connect(self):
        """Connect (or reconnect) to RabbitMQ."""
        try:
            credentials = pika.PlainCredentials(self.user, self.password)
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.host,
                    credentials=credentials,
                    heartbeat=30,
                )
            )
            self.channel = self.connection.channel()
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type="fanout",
                durable=True,
            )
            q = self.channel.queue_declare(queue="", exclusive=True)
            self.queue_name = q.method.queue
            logger.info("RabbitMQ connected on %s", self.host)
        except Exception as e:
            logger.warning("RabbitMQ connect failed: %r, using fallback", e)
            raise e

    def publish(self, routing_key: str, payload: dict) -> None:
        try:
            if not self.connection or self.connection.is_closed:
                self._connect()
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(payload),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # persistent
                ),
            )
        except Exception as e:
            logger.warning("RabbitMQ publish failed: %r, fallback triggered", e)

    def subscribe(self, routing_keys: List[str], on_message: Callable[[Dict], None]) -> None:
        # In fanout exchange routing_keys are ignored; bind the queue once.
        try:
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=self.queue_name,
                routing_key="",
            )
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=lambda ch, method, properties, body: on_message(
                    json.loads(body.decode("utf-8"))
                ),
                auto_ack=True,
            )
        except Exception as e:
            logger.warning("RabbitMQ subscribe failed: %r", e)

    def process_events(self, time_limit: float = 0) -> None:
        """Process any pending RabbitMQ events.

        This method can be called periodically when not using start_consuming().
        """
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.process_data_events(time_limit=time_limit)
        except Exception as e:
            logger.warning("RabbitMQ process_events failed: %r", e)

    def close(self) -> None:
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
        except Exception:
            pass


class InMemoryMessenger(SwarmMessenger):
    """Fallback when RabbitMQ is unavailable."""

    def __init__(self):
        self._callbacks: Dict[str, List[Callable]] = {}

    def publish(self, routing_key: str, payload: dict) -> None:
        callbacks = self._callbacks.get(routing_key, [])
        for cb in callbacks:
            cb(payload)

    def subscribe(self, routing_keys: List[str], on_message: Callable[[Dict], None]) -> None:
        for key in routing_keys:
            if key not in self._callbacks:
                self._callbacks[key] = []
            self._callbacks[key].append(on_message)

    def close(self) -> None:
        self._callbacks.clear()


def create_messenger(config: dict) -> SwarmMessenger:
    host = config["rabbit_host"]
    user = config["rabbit_user"]
    password = config["rabbit_password"]
    try:
        return RabbitMQMessenger(host, user, password)
    except Exception:
        logger.warning("RabbitMQ failed; falling back to in‑memory messenger.")
        return InMemoryMessenger()
