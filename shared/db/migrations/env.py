"""
Alembic environment configuration for the SRE Agent Swarm agent database.

Manages migrations for the `postgres-agents` PostgreSQL database
(Incident, Anomaly, AgentHeartbeat tables).

Run migrations with:
  alembic upgrade head       # Apply all pending migrations
  alembic downgrade -1       # Roll back one migration
  alembic revision --autogenerate -m "description"  # Create new migration
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Alembic Config — brings in the .ini values
# ---------------------------------------------------------------------------

config = context.config

# Configure Python logging from alembic.ini [logging] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import shared models so Alembic autogenerate sees them
# ---------------------------------------------------------------------------

# Ensure shared package is importable (useful when running locally without install)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.db.models import Base  # noqa: E402  — must come after sys.path fix

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_url() -> str:
    """Build DB URL from env, falling back to Alembic ini value."""
    from shared.config.settings import settings
    return settings.agents_db_url.replace("+asyncpg", "")  # Alembic needs sync driver


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection needed)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to DB)."""
    ini_section = config.get_section(config.config_ini_section, {})
    ini_section["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
