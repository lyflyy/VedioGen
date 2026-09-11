from collections.abc import Generator

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def ensure_runtime_schema() -> None:
    """Keep existing local MVP databases readable with additive changes only."""
    tables = {
        "model_invocations": {"provider_request_id": "VARCHAR(255)", "provider_model_id": "VARCHAR(200)"},
        "generation_runs": {"request_data": "JSON", "error_message": "TEXT"},
        "advisor_runs": {"input_fingerprint": "VARCHAR(64)"},
    }
    with engine.begin() as connection:
        for table, additions in tables.items():
            columns = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, sql_type in additions.items():
                if name not in columns:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
