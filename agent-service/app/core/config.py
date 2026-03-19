from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    lardi_connector_url: str = "http://lardi-connector:8002"
    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openrouter/auto"
    fuel_consumption_l_per_100km: float = 30.0
    margin_overhead_coefficient: float = 1.0
    agent_node_timeout_seconds: int = 15

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
