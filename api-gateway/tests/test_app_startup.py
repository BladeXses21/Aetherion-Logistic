"""Smoke test: FastAPI app instantiates without errors."""
from app.main import app


def test_app_is_fastapi_instance():
    from fastapi import FastAPI
    assert isinstance(app, FastAPI)


def test_app_title():
    assert app.title == "Aetherion API Gateway"


def test_settings_loads():
    from app.core.config import settings
    assert settings.redis_url.startswith("redis://")
    assert settings.postgres_url.startswith("postgresql")
