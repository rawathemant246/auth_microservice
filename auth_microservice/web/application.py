import logging
import os
from importlib import metadata
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI
from fastapi.responses import UJSONResponse
from fastapi.staticfiles import StaticFiles
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from auth_microservice.log import configure_logging
from auth_microservice.settings import settings
from auth_microservice.web.api.router import api_router
from auth_microservice.web.lifespan import lifespan_setup

APP_ROOT = Path(__file__).parent.parent

_is_prod = os.environ.get("AUTH_MICROSERVICE_ENVIRONMENT", "development") == "production"

# CRITICAL: Refuse to start with default JWT secret in production.
if _is_prod:
    if settings.jwt_secret_key in ("change-me", "replace-with-strong-secret-min-32-chars", ""):
        raise RuntimeError("JWT secret must be changed from default in production!")


def get_app() -> FastAPI:
    """
    Get FastAPI application.

    This is the main constructor of an application.

    :return: application.
    """
    configure_logging()
    if settings.sentry_dsn:
        # Enables sentry integration.
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_sample_rate,
            environment=settings.environment,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                LoggingIntegration(
                    level=logging.getLevelName(
                        settings.log_level.value,
                    ),
                    event_level=logging.ERROR,
                ),
                SqlalchemyIntegration(),
            ],
        )
    app = FastAPI(
        title="auth_microservice",
        version=metadata.version("auth_microservice"),
        lifespan=lifespan_setup,
        docs_url=None,
        redoc_url=None,
        openapi_url=None if _is_prod else "/api/openapi.json",
        default_response_class=UJSONResponse,
    )

    # Main router for the API.
    app.include_router(router=api_router, prefix="/api")
    # Adds static directory.
    # This directory is used to access swagger files.
    app.mount("/static", StaticFiles(directory=APP_ROOT / "static"), name="static")

    return app
