"""Alembic environment (PR002).

The schema is owned by the `backend/app/models/` package; this file only connects the
migration history to that metadata so autogenerate and `upgrade head` stay in
sync with the ORM. The database URL comes from the application settings
(`BROBOND_DATABASE_URL`), never from this file, so the CLI and the API
bootstrap can never point at different databases.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# The package lives in `backend/`; running the CLI from the repository root
# must still find it (the API image and the tests set PYTHONPATH the same way).
BACKEND_ROOT = str(Path(__file__).resolve().parents[1] / "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.core.config import settings  # noqa: E402
from app.db import Base  # noqa: E402
import app.models  # noqa: E402,F401  — importing registers every table on Base

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False`: the bootstrap runs inside the
    # application process, where the logging configuration already exists
    # (and tests attach their own capture handlers). fileConfig's default
    # would replace the root handlers and disable everything that existed —
    # which would silently kill the app's audit log stream.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
