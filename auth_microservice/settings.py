import enum
import os
from pathlib import Path
from tempfile import gettempdir
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from yarl import URL

TEMP_DIR = Path(gettempdir())

# ── secret strength, checked at boot ────────────────────────────────────────
#
# LMS-backend#16. `jwt_secret_key` used to default to the literal "change-me", and
# the JWT secret is shared with lms-backend -- so a service booting on that default
# will happily sign and verify tokens for any user in any school. It has to refuse
# to start instead.
#
# `internal_api_secret` matters for the same reason from the other direction: when it
# is unset, `internal/views.py` falls *open* for `environment in {"dev", "pytest"}`,
# and "dev" is this class's default. So an unconfigured deployment serves its
# internal endpoints to anybody who can reach the port.

MIN_SECRET_LENGTH = 32

# Substrings, matched case-insensitively. A value containing any of them is a
# placeholder somebody forgot to replace, however long it is -- which is the case
# that a length check alone lets through.
_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "change_me",
    "replace-with",
    "replace_with",
    "internal-secret",
    "internal_secret",
    "your-secret",
    "yoursecret",
    "placeholder",
    "example",
    "insecure",
    "todo",
    "xxxx",
)


def reject_weak_secret(name: str, value: Optional[str]) -> None:
    """Raise unless `value` is a plausible secret.

    Deliberately not gated on environment. A check that only runs in production is a
    check nobody has ever seen run.
    """
    if not value:
        raise ValueError(
            f"{name} is not set. Generate one with `scripts/generate-secrets.sh`; "
            f"this service will not start without it."
        )

    lowered = value.lower()
    for marker in _PLACEHOLDER_MARKERS:
        if marker in lowered:
            raise ValueError(
                f"{name} still contains the placeholder {marker!r}. The JWT secret is "
                f"shared with lms-backend, so a known value forges any user in any "
                f"school. Generate one with `scripts/generate-secrets.sh`."
            )

    if len(value) < MIN_SECRET_LENGTH:
        raise ValueError(
            f"{name} is {len(value)} characters; at least {MIN_SECRET_LENGTH} are "
            f"required. Generate one with `scripts/generate-secrets.sh`."
        )


class LogLevel(str, enum.Enum):
    """Possible log levels."""

    NOTSET = "NOTSET"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"


class Settings(BaseSettings):
    """
    Application settings.

    These parameters can be configured
    with environment variables.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    # quantity of workers for uvicorn
    workers_count: int = 1 # increase number of worker for prod 
    # Enable uvicorn reloading
    reload: bool = False # True for reloading 

    # Current environment
    environment: str = "dev"

    log_level: LogLevel = LogLevel.INFO
    users_secret: str = os.getenv("USERS_SECRET", "")
    bootstrap_secret: str = os.getenv("BOOTSTRAP_SECRET", "")
    metrics_ingest_secret: Optional[str] = os.getenv("METRICS_INGEST_SECRET")
    internal_api_secret: Optional[str] = os.getenv("INTERNAL_API_SECRET")
    # Variables for the database
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "auth_microservice"
    db_pass: str = "auth_microservice"
    db_base: str = "admin"
    db_echo: bool = False

    # Document store (Mongo)
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "auth_documents"

    # JWT configuration
    # No default. It used to be the literal "change-me", which meant a missing
    # environment variable produced a service that signed tokens with a value in the
    # source tree. Validated below.
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires_minutes: int = 30
    jwt_refresh_token_expires_minutes: int = 60 * 24 * 14
    password_reset_token_expires_minutes: int = 60

    # Casdoor and SSO configuration
    casdoor_endpoint: str = "http://localhost:8000"
    casdoor_client_id: str = ""
    casdoor_client_secret: str = ""
    casdoor_organization_name: str = ""
    casdoor_application_name: str = ""

    # Grafana (monitoring) configuration
    grafana_admin_user: Optional[str] = None
    grafana_admin_password: Optional[str] = None

    # Variables for Redis
    redis_host: str = "auth_microservice-redis"
    redis_port: int = 6379
    redis_user: Optional[str] = None
    redis_pass: Optional[str] = None
    redis_base: Optional[int] = None

    # Variables for RabbitMQ
    rabbit_host: str = "auth_microservice-rmq"
    rabbit_port: int = 5672
    rabbit_user: str = "guest"
    rabbit_pass: str = "guest"
    rabbit_vhost: str = "/"

    rabbit_pool_size: int = 2
    rabbit_channel_pool_size: int = 10

    # This variable is used to define
    # multiproc_dir. It's required for [uvi|guni]corn projects.
    prometheus_dir: Path = TEMP_DIR / "prom"

    # Sentry's configuration.
    sentry_dsn: Optional[str] = None
    sentry_sample_rate: float = 1.0

    @property
    def db_url(self) -> URL:
        """
        Assemble database URL from settings.

        :return: database URL.
        """
        return URL.build(
            scheme="postgresql+asyncpg",
            host=self.db_host,
            port=self.db_port,
            user=self.db_user,
            password=self.db_pass,
            path=f"/{self.db_base}",
        )

    @property
    def redis_url(self) -> URL:
        """
        Assemble REDIS URL from settings.

        :return: redis URL.
        """
        path = ""
        if self.redis_base is not None:
            path = f"/{self.redis_base}"
        return URL.build(
            scheme="redis",
            host=self.redis_host,
            port=self.redis_port,
            user=self.redis_user,
            password=self.redis_pass,
            path=path,
        )

    @property
    def rabbit_url(self) -> URL:
        """
        Assemble RabbitMQ URL from settings.

        :return: rabbit URL.
        """
        return URL.build(
            scheme="amqp",
            host=self.rabbit_host,
            port=self.rabbit_port,
            user=self.rabbit_user,
            password=self.rabbit_pass,
            path=self.rabbit_vhost,
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AUTH_MICROSERVICE_",
        env_file_encoding="utf-8",
    )

    @model_validator(mode="after")
    def _secrets_must_be_real(self) -> "Settings":
        """Refuse to start on a placeholder or absent secret.

        Runs when `Settings()` is constructed at import, so the process dies at boot
        with a message naming the variable, rather than serving traffic it cannot
        secure. `pytest` is not exempted: a suite that runs on "change-me" is a suite
        that never exercises this.
        """
        reject_weak_secret("JWT_SECRET_KEY", self.jwt_secret_key)
        reject_weak_secret("INTERNAL_API_SECRET", self.internal_api_secret)
        return self


settings = Settings()
