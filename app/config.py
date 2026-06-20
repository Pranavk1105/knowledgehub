"""Central configuration loaded from environment variables / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "KnowledgeHub"
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # SQLite fallback keeps the app runnable without any external service.
    database_url: str = "sqlite:///./knowledgehub.db"

    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "documents"

    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300


settings = Settings()
