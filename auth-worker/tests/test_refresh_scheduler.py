"""test_refresh_scheduler.py — Тести Story 2.2: Proactive LTSID Refresh Scheduler.

Тестує логіку проактивного оновлення LTSID:
    - TTL < порогу → Chrome refresh запускається, LTSID зберігається
    - TTL > порогу → Chrome НЕ запускається
    - Redis недоступний → WARNING логується, функція завершується без краша
    - Chrome кидає LtsidFetchError → ERROR логується, функція завершується без краша
    - Redis TTL = -1 (ключ без TTL) → refresh запускається
    - Redis TTL = -2 (ключ відсутній) → refresh запускається
    - create_scheduler → повертає налаштований AsyncIOScheduler

Всі тести замінюють реальний Chrome мок-функцією.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.core.errors import ChromeStartupError, LtsidFetchError
from app.scheduler.refresh_scheduler import check_and_refresh_ltsid, create_scheduler
from app.session.ltsid_store import LTSID_REDIS_KEY, ltsid_store

FAKE_LTSID = "abc123fake_ltsid_value_for_tests_xyz"


# ---------------------------------------------------------------------------
# Фікстури
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_ltsid_store():
    """Скидає стан модульного синглтона ltsid_store перед кожним тестом."""
    ltsid_store._ltsid_memory = None
    ltsid_store._mode = "missing"
    yield
    ltsid_store._ltsid_memory = None
    ltsid_store._mode = "missing"


@pytest.fixture
def mock_redis_ok():
    """Мок Redis із TTL=1800 (< 3600) та успішним SET."""
    mock = AsyncMock()
    mock.ttl = AsyncMock(return_value=1800)
    mock.set = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=FAKE_LTSID)
    return mock


@pytest.fixture
def mock_redis_high_ttl():
    """Мок Redis із TTL=7200 (> 3600) — refresh не потрібен."""
    mock = AsyncMock()
    mock.ttl = AsyncMock(return_value=7200)
    return mock


@pytest.fixture
def mock_redis_down():
    """Мок Redis — TTL кидає exception (Redis недоступний)."""
    mock = AsyncMock()
    mock.ttl = AsyncMock(side_effect=Exception("Connection refused"))
    return mock


# ---------------------------------------------------------------------------
# Тести: check_and_refresh_ltsid
# ---------------------------------------------------------------------------


async def test_refresh_triggered_when_ttl_below_threshold(mock_redis_ok):
    """TTL < порогу (1800 < 3600) → Chrome запускається і LTSID зберігається в Redis."""
    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ):
        await check_and_refresh_ltsid(mock_redis_ok)

    # LTSID має бути збережений у Redis
    mock_redis_ok.set.assert_called_once()
    call_args = mock_redis_ok.set.call_args
    assert call_args[0][0] == LTSID_REDIS_KEY
    assert call_args[0][1] == FAKE_LTSID
    # ltsid_store стан оновлений
    assert ltsid_store._mode == "valid"
    assert ltsid_store._ltsid_memory == FAKE_LTSID


async def test_no_refresh_when_ttl_above_threshold(mock_redis_high_ttl):
    """TTL > порогу (7200 > 3600) → Chrome НЕ запускається."""
    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid", new=AsyncMock()
    ) as mock_fetch:
        await check_and_refresh_ltsid(mock_redis_high_ttl)

    mock_fetch.assert_not_called()


async def test_redis_unavailable_logs_warning_no_crash(mock_redis_down):
    """Redis недоступний → WARNING логується, функція завершується без виключення."""
    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid", new=AsyncMock()
    ) as mock_fetch:
        # Не повинна кидати виключення
        await check_and_refresh_ltsid(mock_redis_down)

    # Chrome НЕ запускається при недоступному Redis
    mock_fetch.assert_not_called()
    # ltsid_store залишається без змін (missing)
    assert ltsid_store._mode == "missing"


async def test_chrome_ltsid_fetch_error_no_crash(mock_redis_ok):
    """Chrome кидає LtsidFetchError → ERROR логується, функція НЕ падає."""
    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid",
        new=AsyncMock(side_effect=LtsidFetchError("login failed")),
    ):
        # Не повинна кидати виключення
        await check_and_refresh_ltsid(mock_redis_ok)

    # LTSID НЕ зберігається при помилці Chrome
    mock_redis_ok.set.assert_not_called()
    assert ltsid_store._mode == "missing"


async def test_chrome_startup_error_no_crash(mock_redis_ok):
    """Chrome кидає ChromeStartupError → ERROR логується, функція НЕ падає."""
    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid",
        new=AsyncMock(side_effect=ChromeStartupError("no chrome")),
    ):
        await check_and_refresh_ltsid(mock_redis_ok)

    mock_redis_ok.set.assert_not_called()
    assert ltsid_store._mode == "missing"


async def test_refresh_triggered_when_ttl_is_minus_one():
    """TTL = -1 (ключ існує але без TTL) → refresh запускається."""
    mock_redis = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=-1)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=FAKE_LTSID)

    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ) as mock_fetch:
        await check_and_refresh_ltsid(mock_redis)

    mock_fetch.assert_called_once()
    mock_redis.set.assert_called_once()


async def test_refresh_triggered_when_ttl_is_minus_two():
    """TTL = -2 (ключ не існує) → refresh запускається."""
    mock_redis = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=-2)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=FAKE_LTSID)

    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ) as mock_fetch:
        await check_and_refresh_ltsid(mock_redis)

    mock_fetch.assert_called_once()
    mock_redis.set.assert_called_once()


async def test_refresh_exactly_at_threshold_triggers_refresh():
    """TTL точно дорівнює порогу (3600) → НЕ рахується як нижче порогу, refresh не запускається.

    Умова: ttl < threshold (строго менший), тому ttl == threshold → refresh НЕ потрібен.
    """
    mock_redis = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=3600)

    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid", new=AsyncMock()
    ) as mock_fetch:
        await check_and_refresh_ltsid(mock_redis)

    mock_fetch.assert_not_called()


async def test_refresh_one_second_below_threshold_triggers():
    """TTL = 3599 (рівно на 1 секунду нижче порогу) → refresh запускається."""
    mock_redis = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=3599)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=FAKE_LTSID)

    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ) as mock_fetch:
        await check_and_refresh_ltsid(mock_redis)

    mock_fetch.assert_called_once()


async def test_refresh_calls_fetch_ltsid_with_correct_settings(mock_redis_ok):
    """fetch_ltsid викликається з правильними параметрами з settings."""
    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ) as mock_fetch:
        with patch("app.scheduler.refresh_scheduler.settings") as mock_settings:
            mock_settings.lardi_login = "user@test.com"
            mock_settings.lardi_password = "secret"
            mock_settings.chrome_timeout_seconds = 60
            mock_settings.ltsid_ttl_hours = 23
            mock_settings.ltsid_refresh_threshold_seconds = 3600

            # Переконуємося що TTL менший за поріг
            mock_redis_ok.ttl = AsyncMock(return_value=1800)

            await check_and_refresh_ltsid(mock_redis_ok)

    mock_fetch.assert_called_once_with(
        login="user@test.com",
        password="secret",
        timeout_seconds=60,
    )


async def test_refresh_completed_log_has_correct_ttl(mock_redis_ok):
    """ltsid_store.store викликається з правильними параметрами."""
    with patch(
        "app.scheduler.refresh_scheduler.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ):
        await check_and_refresh_ltsid(mock_redis_ok)

    # TTL у секундах = ltsid_ttl_hours * 3600 = 23 * 3600 = 82800
    call_kwargs = mock_redis_ok.set.call_args[1]
    assert call_kwargs.get("ex") == 23 * 3600


# ---------------------------------------------------------------------------
# Тести: create_scheduler
# ---------------------------------------------------------------------------


def test_create_scheduler_returns_asyncio_scheduler():
    """create_scheduler повертає AsyncIOScheduler."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    mock_redis = AsyncMock()
    scheduler = create_scheduler(mock_redis)

    assert isinstance(scheduler, AsyncIOScheduler)


def test_create_scheduler_has_job_configured():
    """Scheduler містить задачу ltsid_proactive_refresh."""
    mock_redis = AsyncMock()
    scheduler = create_scheduler(mock_redis)
    jobs = scheduler.get_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "ltsid_proactive_refresh"


def test_create_scheduler_job_has_correct_function():
    """Задача планувальника вказує на check_and_refresh_ltsid."""
    mock_redis = AsyncMock()
    scheduler = create_scheduler(mock_redis)
    job = scheduler.get_jobs()[0]

    assert job.func == check_and_refresh_ltsid


def test_create_scheduler_passes_redis_client_as_arg():
    """Задача планувальника передає redis_client як аргумент."""
    mock_redis = AsyncMock()
    scheduler = create_scheduler(mock_redis)
    job = scheduler.get_jobs()[0]

    # APScheduler 3.x зберігає args як tuple
    assert job.args == (mock_redis,)
