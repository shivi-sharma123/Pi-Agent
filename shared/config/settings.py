"""
Centralised configuration management via Pydantic BaseSettings.

All services and agents import Settings from here.  Values are read from:
  1. Environment variables (highest priority)
  2. A .env file in the project root

Usage::

    from shared.config.settings import settings

    db_url = settings.agents_db_url
    nats_url = settings.nats_url
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application-wide configuration.

    All fields can be overridden via environment variables of the same name
    (uppercased).  For example, NATS_URL=nats://custom-host:4222.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Environment                                                          #
    # ------------------------------------------------------------------ #
    environment: str = Field(default="development", description="deployment env (development/staging/production)")
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="'json' or 'console'")

    # ------------------------------------------------------------------ #
    # NATS                                                                 #
    # ------------------------------------------------------------------ #
    nats_url: str = Field(default="nats://localhost:4222", description="NATS connection URL")
    nats_max_reconnect_attempts: int = Field(default=10)
    nats_reconnect_time_wait: float = Field(default=2.0, description="seconds between reconnect attempts")

    # ------------------------------------------------------------------ #
    # PostgreSQL — agent incident store                                   #
    # ------------------------------------------------------------------ #
    agents_db_host: str = Field(default="localhost")
    agents_db_port: int = Field(default=5432)
    agents_db_name: str = Field(default="agents")
    agents_db_user: str = Field(default="postgres")
    agents_db_password: str = Field(default="postgres")

    @property
    def agents_db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.agents_db_user}:{self.agents_db_password}"
            f"@{self.agents_db_host}:{self.agents_db_port}/{self.agents_db_name}"
        )

    # ------------------------------------------------------------------ #
    # PostgreSQL — orders store                                           #
    # ------------------------------------------------------------------ #
    orders_db_host: str = Field(default="localhost")
    orders_db_port: int = Field(default=5433)
    orders_db_name: str = Field(default="orders")
    orders_db_user: str = Field(default="postgres")
    orders_db_password: str = Field(default="postgres")

    @property
    def orders_db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.orders_db_user}:{self.orders_db_password}"
            f"@{self.orders_db_host}:{self.orders_db_port}/{self.orders_db_name}"
        )

    # ------------------------------------------------------------------ #
    # PostgreSQL — payments store                                         #
    # ------------------------------------------------------------------ #
    payments_db_host: str = Field(default="localhost")
    payments_db_port: int = Field(default=5434)
    payments_db_name: str = Field(default="payments")
    payments_db_user: str = Field(default="postgres")
    payments_db_password: str = Field(default="postgres")

    @property
    def payments_db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.payments_db_user}:{self.payments_db_password}"
            f"@{self.payments_db_host}:{self.payments_db_port}/{self.payments_db_name}"
        )

    # ------------------------------------------------------------------ #
    # Redis                                                                #
    # ------------------------------------------------------------------ #
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: Optional[str] = Field(default=None)
    redis_db: int = Field(default=0)

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ------------------------------------------------------------------ #
    # Observability                                                        #
    # ------------------------------------------------------------------ #
    prometheus_url: str = Field(default="http://localhost:9090")
    loki_url: str = Field(default="http://localhost:3100")
    tempo_url: str = Field(default="http://localhost:3200")

    # ------------------------------------------------------------------ #
    # Services (for inter-service HTTP calls)                              #
    # ------------------------------------------------------------------ #
    user_service_url: str = Field(default="http://user-svc:8001")
    auth_service_url: str = Field(default="http://auth-svc:8004")
    order_service_url: str = Field(default="http://order-svc:8002")
    payment_service_url: str = Field(default="http://payment-svc:8005")
    product_service_url: str = Field(default="http://product-svc:8003")
    search_service_url: str = Field(default="http://search-svc:8006")

    # ------------------------------------------------------------------ #
    # Agent settings                                                       #
    # ------------------------------------------------------------------ #
    agent_heartbeat_interval_seconds: int = Field(default=30, description="Heartbeat publish frequency")
    agent_heartbeat_timeout_seconds: int = Field(default=90, description="Mark agent dead after this many seconds without a heartbeat")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.

    Use this instead of instantiating Settings directly so that the .env file
    is only parsed once per process.
    """
    return Settings()


# Module-level singleton — import this directly in most cases.
settings: Settings = get_settings()
