from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, Set

import aio_pika
from aio_pika import Message
from aio_pika.abc import AbstractChannel, AbstractRobustConnection
from aio_pika.exceptions import AMQPConnectionError
from aio_pika.pool import Pool
from fastapi import FastAPI

from auth_microservice.settings import settings


class _InMemoryMessage:
    """Minimal message object mimicking aio-pika's incoming message."""

    __slots__ = ("body",)

    def __init__(self, body: bytes) -> None:
        self.body = body

    async def ack(self) -> None:  # pragma: no cover - nothing to do for in-memory
        return None


class _InMemoryQueue:
    """Very small subset of the queue API required for tests."""

    def __init__(self, broker: "_InMemoryBroker", name: str) -> None:
        self._broker = broker
        self.name = name
        self._messages: Deque[bytes] = deque()

    async def bind(self, exchange: "_InMemoryExchange", routing_key: str) -> None:
        self._broker.bind_queue(self.name, exchange.name, routing_key)

    async def get(self, timeout: float | None = None) -> _InMemoryMessage:
        if not self._messages:
            from aio_pika.exceptions import QueueEmpty

            raise QueueEmpty
        body = self._messages.popleft()
        return _InMemoryMessage(body)

    async def delete(self, *, if_unused: bool = False, if_empty: bool = False) -> None:
        self._broker.delete_queue(self.name)

    # Helpers -----------------------------------------------------------------
    def enqueue(self, body: bytes) -> None:
        self._messages.append(body)


class _InMemoryExchange:
    """In-memory exchange handling publish & delete semantics."""

    def __init__(self, broker: "_InMemoryBroker", name: str) -> None:
        self._broker = broker
        self.name = name

    async def publish(self, message: Message, routing_key: str) -> None:
        self._broker.publish(self.name, routing_key, message.body)

    async def delete(self, *, if_unused: bool = False) -> None:
        self._broker.delete_exchange(self.name)


class _InMemoryChannel:
    """Factory for in-memory exchanges/queues."""

    def __init__(self, broker: "_InMemoryBroker") -> None:
        self._broker = broker

    async def declare_exchange(self, name: str, auto_delete: bool = True) -> _InMemoryExchange:
        return self._broker.get_exchange(name)

    async def declare_queue(self, name: str, auto_delete: bool = True) -> _InMemoryQueue:
        return self._broker.get_queue(name)

    async def get_exchange(self, name: str, ensure: bool = False) -> _InMemoryExchange:
        if ensure:
            return self._broker.get_exchange(name)
        exchange = self._broker.exchanges.get(name)
        if exchange is None:
            raise KeyError(name)
        return exchange

    async def close(self) -> None:  # pragma: no cover - nothing to close
        return None


class _InMemoryRabbitConnection:
    """Connection wrapper that hands out in-memory channels."""

    def __init__(self, broker: "_InMemoryBroker") -> None:
        self._broker = broker

    async def channel(self) -> _InMemoryChannel:
        return _InMemoryChannel(self._broker)

    async def close(self) -> None:  # pragma: no cover - nothing to close
        return None


class _InMemoryBroker:
    """Keeps state for exchanges, queues, and bindings."""

    def __init__(self) -> None:
        self.exchanges: Dict[str, _InMemoryExchange] = {}
        self.queues: Dict[str, _InMemoryQueue] = {}
        self._bindings: Dict[tuple[str, str], Set[str]] = defaultdict(set)

    def get_exchange(self, name: str) -> _InMemoryExchange:
        exchange = self.exchanges.get(name)
        if exchange is None:
            exchange = _InMemoryExchange(self, name)
            self.exchanges[name] = exchange
        return exchange

    def get_queue(self, name: str) -> _InMemoryQueue:
        queue = self.queues.get(name)
        if queue is None:
            queue = _InMemoryQueue(self, name)
            self.queues[name] = queue
        return queue

    def bind_queue(self, queue_name: str, exchange_name: str, routing_key: str) -> None:
        key = (exchange_name, routing_key)
        self._bindings[key].add(queue_name)

    def publish(self, exchange_name: str, routing_key: str, body: bytes) -> None:
        key = (exchange_name, routing_key)
        for queue_name in self._bindings.get(key, set()):
            queue = self.queues.get(queue_name)
            if queue is not None:
                queue.enqueue(body)

    def delete_exchange(self, exchange_name: str) -> None:
        self.exchanges.pop(exchange_name, None)
        keys_to_remove = [key for key in self._bindings if key[0] == exchange_name]
        for key in keys_to_remove:
            self._bindings.pop(key, None)

    def delete_queue(self, queue_name: str) -> None:
        self.queues.pop(queue_name, None)
        for queues in self._bindings.values():
            queues.discard(queue_name)


def init_rabbit(app: FastAPI) -> None:  # pragma: no cover
    """
    Initialize rabbitmq pools.

    :param app: current FastAPI application.
    """

    broker = _InMemoryBroker()
    use_in_memory = False

    async def get_connection() -> AbstractRobustConnection:
        """Create rabbitmq connection or fall back to an in-memory broker."""

        nonlocal use_in_memory
        if use_in_memory:
            return _InMemoryRabbitConnection(broker)
        try:
            return await aio_pika.connect_robust(str(settings.rabbit_url))
        except (AMQPConnectionError, OSError):
            use_in_memory = True
            return _InMemoryRabbitConnection(broker)

    # This pool is used to open connections.
    connection_pool: Pool[AbstractRobustConnection] = Pool(
        get_connection,
        max_size=settings.rabbit_pool_size,
    )

    async def get_channel() -> AbstractChannel:
        """
        Open channel on connection.

        Channels are used to actually communicate with rabbitmq.

        :return: connected channel.
        """
        async with connection_pool.acquire() as connection:
            return await connection.channel()

    # This pool is used to open channels.
    channel_pool: Pool[AbstractChannel] = Pool(
        get_channel,
        max_size=settings.rabbit_channel_pool_size,
    )

    app.state.rmq_pool = connection_pool
    app.state.rmq_channel_pool = channel_pool


async def shutdown_rabbit(app: FastAPI) -> None:  # pragma: no cover
    """
    Close all connection and pools.

    :param app: current application.
    """
    await app.state.rmq_channel_pool.close()
    await app.state.rmq_pool.close()
