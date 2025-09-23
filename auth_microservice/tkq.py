from typing import Any

import taskiq_fastapi
from taskiq import AsyncBroker, AsyncResultBackend, InMemoryBroker
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import RedisAsyncResultBackend

from auth_microservice.settings import settings

result_backend: AsyncResultBackend[Any] = RedisAsyncResultBackend(
    redis_url=str(settings.redis_url.with_path("/1")),
)
broker: AsyncBroker = AioPikaBroker(
    str(settings.rabbit_url),
).with_result_backend(result_backend)

if settings.environment.lower() == "pytest":
    broker = InMemoryBroker()

taskiq_fastapi.init(
    broker,
    "auth_microservice.web.application:get_app",
)
