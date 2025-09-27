"""Helpers for publishing domain events via RabbitMQ."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from aio_pika import Message
from aio_pika.abc import AbstractChannel
from aio_pika.pool import Pool
from fastapi import Request


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def _publish(
    pool: Pool[AbstractChannel] | None,
    exchange_name: str,
    routing_key: str,
    payload: dict[str, Any],
) -> None:
    if pool is None:
        return
    body = json.dumps(payload, default=_serialize).encode("utf-8")
    async with pool.acquire() as channel:
        exchange = await channel.declare_exchange(exchange_name, auto_delete=False)
        message = Message(body=body, content_type="application/json", delivery_mode=2)
        await exchange.publish(message, routing_key=routing_key)


async def publish_security_event(request: Request, event_type: str, payload: dict[str, Any]) -> None:
    pool: Pool[AbstractChannel] | None = getattr(request.app.state, "rmq_channel_pool", None)
    enriched = {
        "type": event_type,
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await _publish(pool, "security.events", event_type, enriched)


async def publish_audit_event(request: Request, event_type: str, payload: dict[str, Any]) -> None:
    pool: Pool[AbstractChannel] | None = getattr(request.app.state, "rmq_channel_pool", None)
    enriched = {
        "type": event_type,
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await _publish(pool, "audit.events", event_type, enriched)


async def publish_email_event(request: Request, event_type: str, payload: dict[str, Any]) -> None:
    pool: Pool[AbstractChannel] | None = getattr(request.app.state, "rmq_channel_pool", None)
    await _publish(pool, "email.events", event_type, payload)


async def publish_log_ingest(request: Request, event_type: str, payload: dict[str, Any]) -> None:
    pool: Pool[AbstractChannel] | None = getattr(request.app.state, "rmq_channel_pool", None)
    await _publish(pool, "logs.ingest", event_type, payload)
