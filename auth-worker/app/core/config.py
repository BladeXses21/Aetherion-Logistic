from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    lardi_login: str = ""
    lardi_password: str = ""
    admin_api_key: str = "changeme-replace-in-production"
    ltsid_ttl_hours: int = 23
    fuel_cache_ttl_seconds: int = 3600
    ltsid_refresh_lock_ttl_seconds: int = 120
    chrome_timeout_seconds: int = 60
    ltsid_refresh_wait_seconds: int = 90
    refresh_circuit_breaker_threshold: int = 3
    refresh_circuit_breaker_pause_minutes: int = 10
    fuel_price_url: str = ""
    fuel_price_http_timeout_seconds: int = 5
    fuel_price_css_selector: str = ""

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
