import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Import Base and all models so Alembic knows which tables to create.
# If a model is not imported here, Alembic won't see it and won't create the table.
from app.models import Base  # noqa: F401
import app.models.repository  # noqa: F401
import app.models.document    # noqa: F401
import app.models.commit      # noqa: F401
import app.models.bom         # noqa: F401
import app.models.revision          # noqa: F401
import app.models.audit             # noqa: F401
import app.models.revision_request  # noqa: F401
import app.models.user              # noqa: F401
import app.models.role              # noqa: F401

config = context.config

# Read DATABASE_URL from environment — never hardcoded
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is what Alembic compares against the real database to find what needs to change
target_metadata = Base.metadata


def run_migrations_offline():
    # "offline" mode generates SQL scripts without connecting to the database
    context.configure(
        url=os.environ["DATABASE_URL"],
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # "online" mode connects to the database and applies migrations directly
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
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
