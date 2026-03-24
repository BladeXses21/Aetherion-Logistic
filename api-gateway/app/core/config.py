from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_url: str = "postgresql+asyncpg://aetherion:aetherion@postgres:5432/aetherion"
    redis_url: str = "redis://redis:6379/0"
    agent_service_url: str = "http://agent-service:8001"
    admin_api_key: str = "changeme-replace-in-production"
    allowed_origins: str = "*"

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
