from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./.data/vediogen.db"
    data_dir: Path = Path(".data")
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VEDIOGEN_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
