from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    lardi_base_url: str = "https://lardi-trans.com"
    lardi_http_timeout_seconds: int = 10
    lardi_request_min_interval_seconds: float = 1.0

    # Максимальний час очікування нового LTSID після запиту на refresh (секунди)
    ltsid_refresh_wait_seconds: int = 90
    # Затримка перед повторним запитом після успішного refresh LTSID (мілісекунди)
    ltsid_retry_delay_ms: int = 200

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
