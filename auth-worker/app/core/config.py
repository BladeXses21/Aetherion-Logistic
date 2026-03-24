"""config.py — Типізована конфігурація auth-worker через pydantic-settings.

Всі значення читаються з ENV змінних (або .env файлу).
Валідація виконується автоматично при старті сервісу — якщо обов'язкова
змінна відсутня або має неправильний тип, сервіс відмовить з описом помилки.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Налаштування auth-worker сервісу.

    Всі поля відповідають ENV змінним (case-insensitive).
    Значення за замовчуванням безпечні для dev-середовища.
    """

    redis_url: str = "redis://redis:6379/0"
    lardi_login: str = ""
    lardi_password: str = ""
    admin_api_key: str = "changeme-replace-in-production"
    ltsid_ttl_hours: int = 23
    fuel_cache_ttl_seconds: int = 3600
    ltsid_refresh_lock_ttl_seconds: int = 120  # 2×chrome_timeout (ARCH4 spec: 300 → знижено свідомо)
    chrome_timeout_seconds: int = 60
    ltsid_refresh_wait_seconds: int = 90
    refresh_circuit_breaker_threshold: int = 3
    refresh_circuit_breaker_pause_minutes: int = 10
    # WOG API — повертає ціни всіх видів палива; беремо ДП Євро5 для вантажівок
    fuel_price_url: str = "https://api.wog.ua/fuel_stations"
    fuel_price_http_timeout_seconds: int = 5
    fuel_price_css_selector: str = ""

    # Story 2.2: Proactive LTSID Refresh Scheduler
    ltsid_proactive_check_interval_seconds: int = 1800  # 30 хвилин між перевірками TTL
    ltsid_refresh_threshold_seconds: int = 3600  # поріг TTL для proactive refresh (1 година)

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
