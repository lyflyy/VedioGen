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
    """Apply the two additive columns needed by pre-migration local databases."""
    columns = {column["name"] for column in inspect(engine).get_columns("model_invocations")}
    additions = {
        "provider_request_id": "VARCHAR(255)",
        "provider_model_id": "VARCHAR(200)",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in columns:
                connection.exec_driver_sql(f"ALTER TABLE model_invocations ADD COLUMN {name} {sql_type}")
