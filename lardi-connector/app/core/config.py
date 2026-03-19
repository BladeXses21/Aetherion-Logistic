from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    lardi_base_url: str = "https://lardi-trans.com"
    lardi_http_timeout_seconds: int = 10
    lardi_request_min_interval_seconds: float = 1.0

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
