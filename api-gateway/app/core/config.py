"""
config.py — Налаштування api-gateway через змінні середовища.

Всі параметри читаються з .env файлу або ENV змінних Docker.
JWT параметри потрібні для Epic 9.1 (автентифікація через JWT).
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Конфігурація api-gateway.

    Attributes:
        postgres_url: URL підключення до PostgreSQL.
        redis_url: URL підключення до Redis.
        agent_service_url: Внутрішня URL agent-service.
        admin_api_key: Ключ для захисту адмін-ендпоінтів (X-API-Key).
        allowed_origins: Дозволені CORS origins (через кому).
        jwt_secret_key: Секретний ключ для підпису JWT токенів. ОБОВ'ЯЗКОВО змінити у продакшені.
        jwt_algorithm: Алгоритм підпису JWT (HS256).
        access_token_expire_minutes: TTL access JWT токена в хвилинах (24год = 1440хв).
    """
    postgres_url: str = "postgresql+asyncpg://aetherion:aetherion@postgres:5432/aetherion"
    redis_url: str = "redis://redis:6379/0"
    agent_service_url: str = "http://agent-service:8001"
    admin_api_key: str = "changeme-replace-in-production"
    allowed_origins: str = "*"

    # JWT автентифікація (Epic 9.1)
    jwt_secret_key: str = "changeme-jwt-secret-replace-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 години

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
