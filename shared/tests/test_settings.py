"""
Unit tests for Pydantic Settings (shared/config/settings.py).

These tests verify the config defaults and URL property helpers without
requiring actual environment variables or .env files.
"""

from __future__ import annotations

import os

import pytest


class TestSettings:
    def test_default_nats_url(self, monkeypatch):
        # Ensure no env override
        monkeypatch.delenv("NATS_URL", raising=False)
        from importlib import reload
        import shared.config.settings as mod
        reload(mod)
        s = mod.Settings()
        assert s.nats_url == "nats://localhost:4222"

    def test_agents_db_url_is_built_from_parts(self):
        from shared.config.settings import Settings
        s = Settings(
            agents_db_host="myhost",
            agents_db_port=5432,
            agents_db_name="testdb",
            agents_db_user="admin",
            agents_db_password="secret",
        )
        assert "myhost" in s.agents_db_url
        assert "testdb" in s.agents_db_url
        assert "admin" in s.agents_db_url
        assert "asyncpg" in s.agents_db_url

    def test_redis_url_without_password(self):
        from shared.config.settings import Settings
        s = Settings(redis_host="redis-host", redis_port=6379, redis_password=None)
        url = s.redis_url
        assert "redis-host" in url
        assert "@" not in url  # no auth part

    def test_redis_url_with_password(self):
        from shared.config.settings import Settings
        s = Settings(redis_host="redis-host", redis_port=6379, redis_password="pass123")
        url = s.redis_url
        assert ":pass123@" in url

    def test_environment_override(self, monkeypatch):
        monkeypatch.setenv("NATS_URL", "nats://custom-host:9999")
        from shared.config.settings import Settings
        s = Settings()
        assert s.nats_url == "nats://custom-host:9999"
