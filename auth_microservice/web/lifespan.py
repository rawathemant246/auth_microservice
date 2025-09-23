from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from prometheus_fastapi_instrumentator.instrumentation import (
    PrometheusFastApiInstrumentator,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from auth_microservice.rbac.service import RbacService
from auth_microservice.services.document_store import DocumentStoreService
from auth_microservice.services.rabbit.lifespan import init_rabbit, shutdown_rabbit
from auth_microservice.services.redis.lifespan import init_redis, shutdown_redis
from auth_microservice.services.sso import CasdoorService
from auth_microservice.settings import settings
from auth_microservice.tkq import broker


def _setup_db(app: FastAPI) -> None:  # pragma: no cover
    """
    Creates connection to the database.

    This function creates SQLAlchemy engine instance,
    session_factory for creating sessions
    and stores them in the application's state property.

    :param app: fastAPI application.
    """
    engine = create_async_engine(str(settings.db_url), echo=settings.db_echo)
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    app.state.casdoor_service = CasdoorService()


def _setup_document_store(app: FastAPI) -> None:  # pragma: no cover
    """Initialise MongoDB client and document store service."""

    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    app.state.mongo_client = mongo_client
    app.state.mongo_database = mongo_client[settings.mongodb_database]
    app.state.document_store = DocumentStoreService(app.state.mongo_database)


def setup_prometheus(app: FastAPI) -> None:  # pragma: no cover
    """
    Enables prometheus integration.

    :param app: current application.
    """
    PrometheusFastApiInstrumentator(should_group_status_codes=False).instrument(
        app,
    ).expose(app, should_gzip=True, name="prometheus_metrics")


@asynccontextmanager
async def lifespan_setup(
    app: FastAPI,
) -> AsyncGenerator[None, None]:  # pragma: no cover
    """
    Actions to run on application startup.

    This function uses fastAPI app to store data
    in the state, such as db_engine.

    :param app: the fastAPI application.
    :return: function that actually performs actions.
    """

    app.middleware_stack = None
    if not broker.is_worker_process:
        await broker.startup()
    _setup_db(app)
    _setup_document_store(app)
    rbac_model_path = Path(__file__).resolve().parent.parent / "rbac" / "model.conf"
    app.state.rbac_service = RbacService(app.state.db_session_factory, rbac_model_path)
    await app.state.rbac_service.ensure_policies_loaded()
    init_redis(app)
    init_rabbit(app)
    setup_prometheus(app)
    app.middleware_stack = app.build_middleware_stack()

    yield
    if not broker.is_worker_process:
        await broker.shutdown()
    await app.state.db_engine.dispose()

    app.state.mongo_client.close()

    await shutdown_redis(app)
    await shutdown_rabbit(app)
