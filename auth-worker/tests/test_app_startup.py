"""Smoke test: FastAPI app instantiates without errors."""
from app.main import app


def test_app_is_fastapi_instance():
    from fastapi import FastAPI
    assert isinstance(app, FastAPI)


def test_app_title():
    assert app.title == "Aetherion Auth Worker"


def test_settings_loads():
    from app.core.config import settings
    assert settings.redis_url.startswith("redis://")
    assert settings.ltsid_ttl_hours == 23
    assert settings.ltsid_refresh_lock_ttl_seconds == 120
