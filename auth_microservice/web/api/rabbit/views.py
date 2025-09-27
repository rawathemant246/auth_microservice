from aio_pika import Channel, Message
from aio_pika.pool import Pool
from fastapi import APIRouter, Depends, HTTPException, status

from auth_microservice.services.rabbit.dependencies import get_rmq_channel_pool
from auth_microservice.settings import settings
from auth_microservice.web.api.rabbit.schema import RMQMessageDTO

router = APIRouter()


def _ensure_internal_access() -> None:
    if settings.environment not in {"dev", "pytest"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")


@router.post("/")
async def send_rabbit_message(
    message: RMQMessageDTO,
    _: None = Depends(_ensure_internal_access),
    pool: Pool[Channel] = Depends(get_rmq_channel_pool),
) -> None:
    """
    Posts a message in a rabbitMQ's exchange.

    :param message: message to publish to rabbitmq.
    :param pool: rabbitmq channel pool
    """
    async with pool.acquire() as conn:
        exchange = await conn.declare_exchange(
            name=message.exchange_name,
            auto_delete=True,
        )
        await exchange.publish(
            message=Message(
                body=message.message.encode("utf-8"),
                content_encoding="utf-8",
                content_type="text/plain",
            ),
            routing_key=message.routing_key,
        )
