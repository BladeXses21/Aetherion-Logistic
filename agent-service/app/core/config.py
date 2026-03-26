"""
config.py — Налаштування agent-service через змінні середовища.

Всі параметри читаються з .env файлу або ENV змінних.
Значення за замовчуванням відповідають docker-compose конфігурації.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Конфігурація agent-service.

    Attributes:
        redis_url: URL підключення до Redis (для busy-lock та fuel_price).
        postgres_url: URL підключення до PostgreSQL (для geo_resolver, ua_cities).
        lardi_connector_url: Базовий URL lardi-connector сервісу.
        llm_api_key: API ключ OpenRouter (або іншого OpenAI-сумісного провайдера).
        llm_base_url: Базовий URL LLM провайдера.
        llm_model: Ідентифікатор моделі LLM.
        fuel_consumption_l_per_100km: Витрата палива (л/100км) для розрахунку маржі.
        margin_overhead_coefficient: Коефіцієнт додаткових витрат (множник до fuel_cost).
        agent_node_timeout_seconds: Максимальний час виконання одного вузла графу (сек).
        agent_busy_ttl_seconds: TTL ключа aetherion:agent:busy в Redis (секунди, safety net).
        nominatim_user_agent: User-Agent для Nominatim geocoding запитів.
    """

    redis_url: str = "redis://redis:6379/0"
    postgres_url: str = "postgresql+asyncpg://aetherion:aetherion@postgres:5432/aetherion"
    lardi_connector_url: str = "http://lardi-connector:8002"
    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openrouter/auto"
    llm_max_tokens: int = 2048  # Обмеження токенів відповіді — запобігає 402 на OpenRouter
    fuel_consumption_l_per_100km: float = 30.0
    margin_overhead_coefficient: float = 1.0
    agent_node_timeout_seconds: int = 15
    agent_busy_ttl_seconds: int = 60
    nominatim_user_agent: str = "Aetherion/2.0 (logistics-agent)"

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
