from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./.data/vediogen.db"
    data_dir: Path = Path(".data")
    cors_origins: list[str] = ["http://localhost:3000"]
    allow_fake_provider: bool = False
    allow_external_models: bool = True
    allow_external_search: bool = True
    allow_local_models: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VEDIOGEN_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
