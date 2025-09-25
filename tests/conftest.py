import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Optional
from unittest.mock import Mock

import pytest
from aio_pika import Channel
from aio_pika.abc import AbstractExchange, AbstractQueue
from aio_pika.pool import Pool
from fakeredis import FakeServer
from fakeredis.aioredis import FakeConnection
from fastapi import FastAPI
from httpx import AsyncClient
from redis.asyncio import ConnectionPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.utils import create_database, drop_database
from auth_microservice.services.rabbit.dependencies import get_rmq_channel_pool
from auth_microservice.services.rabbit.lifespan import init_rabbit, shutdown_rabbit
from auth_microservice.services.redis.dependency import get_redis_pool
from auth_microservice.settings import settings
from auth_microservice.web.application import get_app


class InMemoryDocumentStore:
    """Simple in-memory substitute for the Mongo-backed document store."""

    def __init__(self) -> None:
        self._org_settings: dict[int, dict[str, Any]] = {}
        self._privacy_settings: dict[int, dict[str, Any]] = {}
        self._feedback: dict[str, dict[str, Any]] = {}

    async def get_organization_settings(self, organization_id: int) -> dict[str, Any] | None:
        settings = self._org_settings.get(organization_id)
        return None if settings is None else dict(settings)

    async def upsert_organization_settings(
        self,
        organization_id: int,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        self._org_settings[organization_id] = dict(settings)
        return dict(settings)

    async def get_privacy_settings(self, organization_id: int) -> dict[str, Any] | None:
        settings = self._privacy_settings.get(organization_id)
        return None if settings is None else dict(settings)

    async def upsert_privacy_settings(
        self,
        organization_id: int,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        self._privacy_settings[organization_id] = dict(settings)
        return dict(settings)

    async def create_feedback(
        self,
        *,
        organization_id: int,
        user_id: int,
        content: str,
        category: str,
        status: str,
    ) -> dict[str, Any]:
        feedback_id = uuid.uuid4().hex
        now = datetime.utcnow().isoformat()
        document = {
            "feedback_id": feedback_id,
            "organization_id": organization_id,
            "user_id": user_id,
            "content": content,
            "category": category,
            "status": status,
            "created_at": now,
            "updated_at": now,
        }
        self._feedback[feedback_id] = document
        return dict(document)

    async def list_feedback(
        self,
        *,
        organization_id: int,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for document in self._feedback.values():
            if document["organization_id"] != organization_id:
                continue
            if user_id is not None and document["user_id"] != user_id:
                continue
            if status is not None and document["status"] != status:
                continue
            results.append(dict(document))
        return results

    async def update_feedback(
        self,
        feedback_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        document = self._feedback.get(feedback_id)
        if document is None:
            return None
        document.update(updates)
        document["updated_at"] = datetime.utcnow().isoformat()
        return dict(document)

    async def search_feedback(
        self,
        *,
        organization_id: int,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        lowered = query.lower()
        results: list[dict[str, Any]] = []
        for document in self._feedback.values():
            if document["organization_id"] != organization_id:
                continue
            text = " ".join(
                [
                    str(document.get("content", "")),
                    str(document.get("category", "")),
                    str(document.get("status", "")),
                ]
            ).lower()
            if lowered in text:
                results.append(dict(document))
            if len(results) >= limit:
                break
        return results

    async def get_user_feedback(
        self,
        organization_id: int,
        user_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        return await self.list_feedback(
            organization_id=organization_id,
            user_id=user_id,
        )


class StubRbacService:
    async def invalidate_cache(self) -> None:  # noqa: D401 - simple stub
        return None

    async def enforce(
        self,
        *,
        user_id: int,
        permission_name: str,
        organization_id: int,
        action: str = "access",
    ) -> bool:
        return True

    async def get_user_permissions(self, user_id: int, organization_id: int) -> list[str]:  # noqa: ARG002
        return []


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """
    Backend for anyio pytest plugin.

    :return: backend name.
    """
    return "asyncio"


@pytest.fixture(scope="session")
async def _engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Create engine and databases.

    :yield: new engine.
    """
    from auth_microservice.db.meta import meta
    from auth_microservice.db.models import load_all_models

    load_all_models()

    await create_database()

    engine = create_async_engine(str(settings.db_url))
    async with engine.begin() as conn:
        await conn.run_sync(meta.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()
        await drop_database()


@pytest.fixture
async def dbsession(
    _engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get session to database.

    Fixture that returns a SQLAlchemy session with a SAVEPOINT, and the rollback to it
    after the test completes.

    :param _engine: current engine.
    :yields: async session.
    """
    connection = await _engine.connect()
    trans = await connection.begin()

    session_maker = async_sessionmaker(
        connection,
        expire_on_commit=False,
    )
    session = session_maker()

    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await connection.close()


@pytest.fixture
async def test_rmq_pool() -> AsyncGenerator[Channel, None]:
    """
    Create rabbitMQ pool.

    :yield: channel pool.
    """
    app_mock = Mock()
    init_rabbit(app_mock)
    yield app_mock.state.rmq_channel_pool
    await shutdown_rabbit(app_mock)


@pytest.fixture
async def test_exchange_name() -> str:
    """
    Name of an exchange to use in tests.

    :return: name of an exchange.
    """
    return uuid.uuid4().hex


@pytest.fixture
async def test_routing_key() -> str:
    """
    Name of routing key to use while binding test queue.

    :return: key string.
    """
    return uuid.uuid4().hex


@pytest.fixture
async def test_exchange(
    test_exchange_name: str,
    test_rmq_pool: Pool[Channel],
) -> AsyncGenerator[AbstractExchange, None]:
    """
    Creates test exchange.

    :param test_exchange_name: name of an exchange to create.
    :param test_rmq_pool: channel pool for rabbitmq.
    :yield: created exchange.
    """
    async with test_rmq_pool.acquire() as conn:
        exchange = await conn.declare_exchange(
            name=test_exchange_name,
            auto_delete=True,
        )
        yield exchange

        await exchange.delete(if_unused=False)


@pytest.fixture
async def test_queue(
    test_exchange: AbstractExchange,
    test_rmq_pool: Pool[Channel],
    test_routing_key: str,
) -> AsyncGenerator[AbstractQueue, None]:
    """
    Creates queue connected to exchange.

    :param test_exchange: exchange to bind queue to.
    :param test_rmq_pool: channel pool for rabbitmq.
    :param test_routing_key: routing key to use while binding.
    :yield: queue binded to test exchange.
    """
    async with test_rmq_pool.acquire() as conn:
        queue = await conn.declare_queue(name=uuid.uuid4().hex)
        await queue.bind(
            exchange=test_exchange,
            routing_key=test_routing_key,
        )
        yield queue

        await queue.delete(if_unused=False, if_empty=False)


@pytest.fixture
async def fake_redis_pool() -> AsyncGenerator[ConnectionPool, None]:
    """
    Get instance of a fake redis.

    :yield: FakeRedis instance.
    """
    server = FakeServer()
    server.connected = True
    pool = ConnectionPool(connection_class=FakeConnection, server=server)

    yield pool

    await pool.disconnect()


@pytest.fixture
def fastapi_app(
    dbsession: AsyncSession,
    fake_redis_pool: ConnectionPool,
    test_rmq_pool: Pool[Channel],
    _engine: AsyncEngine,
) -> FastAPI:
    """
    Fixture for creating FastAPI app.

    :return: fastapi app with mocked dependencies.
    """
    application = get_app()
    session_factory = async_sessionmaker(bind=_engine, expire_on_commit=False)

    async def _get_db_session_override() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            async with session.begin():
                yield session

    application.dependency_overrides[get_db_session] = _get_db_session_override
    application.dependency_overrides[get_redis_pool] = lambda: fake_redis_pool
    application.dependency_overrides[get_rmq_channel_pool] = lambda: test_rmq_pool
    application.state.document_store = InMemoryDocumentStore()
    application.state.rbac_service = StubRbacService()
    return application


@pytest.fixture
async def client(
    fastapi_app: FastAPI,
    anyio_backend: Any,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture that creates client for requesting server.

    :param fastapi_app: the application.
    :yield: client for the app.
    """
    async with AsyncClient(app=fastapi_app, base_url="http://test", timeout=2.0) as ac:
        yield ac
