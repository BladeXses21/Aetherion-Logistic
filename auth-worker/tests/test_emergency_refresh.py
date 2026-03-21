"""test_emergency_refresh.py — Тести Story 2.3: Emergency Refresh via Redis Pub/Sub.

Тестує:
    - CircuitBreaker: відкриття після N помилок, скидання після успіху,
      is_open() під час паузи та після її закінчення
    - _do_emergency_refresh: lock acquired → Chrome + LTSID stored
    - _do_emergency_refresh: lock NOT acquired → deduplication polling → INFO log
    - _do_emergency_refresh: Chrome fails → ERROR logged → LTSID not overwritten
    - _do_emergency_refresh: circuit open → Chrome NOT called
    - listen_for_refresh_events: CancelledError → graceful shutdown
    - listen_for_refresh_events: Redis error → reconnect loop (no crash)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.errors import ChromeStartupError, LtsidFetchError
from app.pubsub.emergency_refresh import (
    CircuitBreaker,
    _do_emergency_refresh,
    listen_for_refresh_events,
)
from app.session.ltsid_store import ltsid_store

FAKE_LTSID = "abc123fake_ltsid_value_for_tests_xyz"
REFRESH_LOCK_KEY = "aetherion:auth:refresh:lock"


# ---------------------------------------------------------------------------
# Фікстури
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_ltsid_store():
    """Скидає стан синглтона ltsid_store перед кожним тестом."""
    ltsid_store._ltsid_memory = None
    ltsid_store._mode = "missing"
    yield
    ltsid_store._ltsid_memory = None
    ltsid_store._mode = "missing"


@pytest.fixture
def circuit_breaker():
    """CircuitBreaker з threshold=3, pause=600 секунд."""
    return CircuitBreaker(threshold=3, pause_seconds=600)


@pytest.fixture
def mock_redis_lock_acquired():
    """Мок Redis — SET NX повертає True (lock отримано)."""
    mock = AsyncMock()
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.exists = AsyncMock(return_value=0)
    mock.get = AsyncMock(return_value=FAKE_LTSID)
    return mock


@pytest.fixture
def mock_redis_lock_not_acquired():
    """Мок Redis — SET NX повертає None (lock вже зайнятий)."""
    mock = AsyncMock()
    mock.set = AsyncMock(return_value=None)
    mock.exists = AsyncMock(return_value=0)  # lock одразу звільняється при polling
    return mock


# ---------------------------------------------------------------------------
# Тести: CircuitBreaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_starts_closed(circuit_breaker):
    """Новий CircuitBreaker — circuit закритий."""
    assert not circuit_breaker.is_open()


def test_circuit_breaker_opens_after_threshold(circuit_breaker):
    """Після 3 помилок поспіль circuit відкривається."""
    circuit_breaker.record_failure()
    circuit_breaker.record_failure()
    assert not circuit_breaker.is_open()  # ще не відкритий після 2
    circuit_breaker.record_failure()      # 3-та помилка
    assert circuit_breaker.is_open()


def test_circuit_breaker_resets_counter_after_opening(circuit_breaker):
    """Після відкриття circuit — лічильник помилок скидається до 0."""
    for _ in range(3):
        circuit_breaker.record_failure()
    assert circuit_breaker._consecutive_failures == 0  # скинуто після відкриття


def test_circuit_breaker_record_success_resets_failures(circuit_breaker):
    """record_success() скидає лічильник помилок."""
    circuit_breaker.record_failure()
    circuit_breaker.record_failure()
    circuit_breaker.record_success()
    assert circuit_breaker._consecutive_failures == 0


def test_circuit_breaker_success_does_not_close_open_circuit():
    """Успіх після відкриття circuit НЕ закриває його достроково."""
    cb = CircuitBreaker(threshold=1, pause_seconds=3600)
    cb.record_failure()  # відкриває circuit
    assert cb.is_open()
    cb.record_success()  # скидає лічильник але НЕ закриває
    assert cb.is_open()  # circuit залишається відкритим (пауза ще не скінчилась)


def test_circuit_breaker_closes_after_pause():
    """Circuit закривається автоматично після закінчення паузи."""
    cb = CircuitBreaker(threshold=1, pause_seconds=0)  # пауза 0 секунд
    cb.record_failure()
    # Після 0 секунд паузи circuit має бути закритим
    assert not cb.is_open()


def test_circuit_breaker_logs_warning_on_open(circuit_breaker):
    """record_failure() логує WARNING коли circuit відкривається."""
    with patch("app.pubsub.emergency_refresh.log") as mock_log:
        for _ in range(3):
            circuit_breaker.record_failure()
        mock_log.warning.assert_called_once_with(
            "ltsid_circuit_breaker_open",
            pause_minutes=10,
        )


# ---------------------------------------------------------------------------
# Тести: _do_emergency_refresh — lock acquired
# ---------------------------------------------------------------------------


async def test_do_emergency_refresh_lock_acquired_calls_chrome(
    mock_redis_lock_acquired, circuit_breaker
):
    """Lock отримано → fetch_ltsid викликається."""
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ) as mock_fetch:
        await _do_emergency_refresh(mock_redis_lock_acquired, circuit_breaker)

    mock_fetch.assert_called_once()


async def test_do_emergency_refresh_lock_acquired_stores_ltsid(
    mock_redis_lock_acquired, circuit_breaker
):
    """Lock отримано → LTSID зберігається в Redis."""
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ):
        await _do_emergency_refresh(mock_redis_lock_acquired, circuit_breaker)

    assert ltsid_store._mode == "valid"
    assert ltsid_store._ltsid_memory == FAKE_LTSID


async def test_do_emergency_refresh_lock_acquired_logs_completed(
    mock_redis_lock_acquired, circuit_breaker
):
    """Lock отримано + success → логується INFO 'ltsid_emergency_refresh_completed'."""
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ):
        with patch("app.pubsub.emergency_refresh.log") as mock_log:
            await _do_emergency_refresh(mock_redis_lock_acquired, circuit_breaker)

    mock_log.info.assert_any_call("ltsid_emergency_refresh_completed")


async def test_do_emergency_refresh_lock_acquired_records_success(
    mock_redis_lock_acquired, circuit_breaker
):
    """Успішний refresh → circuit_breaker.record_success() викликано."""
    circuit_breaker.record_failure()  # один failure для перевірки скидання
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ):
        await _do_emergency_refresh(mock_redis_lock_acquired, circuit_breaker)

    assert circuit_breaker._consecutive_failures == 0


async def test_do_emergency_refresh_releases_lock_after_success(
    mock_redis_lock_acquired, circuit_breaker
):
    """Lock видаляється через DELETE після успішного refresh."""
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid",
        new=AsyncMock(return_value=FAKE_LTSID),
    ):
        await _do_emergency_refresh(mock_redis_lock_acquired, circuit_breaker)

    mock_redis_lock_acquired.delete.assert_called_once_with(REFRESH_LOCK_KEY)


# ---------------------------------------------------------------------------
# Тести: _do_emergency_refresh — lock NOT acquired (deduplication)
# ---------------------------------------------------------------------------


async def test_do_emergency_refresh_lock_not_acquired_no_chrome(
    mock_redis_lock_not_acquired, circuit_breaker
):
    """Lock не отримано → Chrome НЕ запускається."""
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid", new=AsyncMock()
    ) as mock_fetch:
        await _do_emergency_refresh(mock_redis_lock_not_acquired, circuit_breaker)

    mock_fetch.assert_not_called()


async def test_do_emergency_refresh_lock_not_acquired_logs_deduplicated(
    mock_redis_lock_not_acquired, circuit_breaker
):
    """Lock не отримано → логується INFO 'ltsid_refresh_deduplicated'."""
    with patch("app.pubsub.emergency_refresh.log") as mock_log:
        await _do_emergency_refresh(mock_redis_lock_not_acquired, circuit_breaker)

    mock_log.info.assert_any_call(
        "ltsid_refresh_deduplicated", reason="lock_held_waited"
    )


# ---------------------------------------------------------------------------
# Тести: _do_emergency_refresh — Chrome fails
# ---------------------------------------------------------------------------


async def test_do_emergency_refresh_chrome_fails_no_ltsid_overwrite(
    mock_redis_lock_acquired, circuit_breaker
):
    """Chrome fail → LTSID НЕ перезаписується."""
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid",
        new=AsyncMock(side_effect=LtsidFetchError("login failed")),
    ):
        await _do_emergency_refresh(mock_redis_lock_acquired, circuit_breaker)

    assert ltsid_store._mode == "missing"  # LTSID не змінився


async def test_do_emergency_refresh_chrome_fails_logs_error(
    mock_redis_lock_acquired, circuit_breaker
):
    """Chrome fail → логується ERROR 'ltsid_emergency_refresh_failed'."""
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid",
        new=AsyncMock(side_effect=ChromeStartupError("no chrome")),
    ):
        with patch("app.pubsub.emergency_refresh.log") as mock_log:
            await _do_emergency_refresh(mock_redis_lock_acquired, circuit_breaker)

    mock_log.error.assert_called_once_with(
        "ltsid_emergency_refresh_failed", exc_info=True
    )


async def test_do_emergency_refresh_chrome_fails_records_failure(
    mock_redis_lock_acquired, circuit_breaker
):
    """Chrome fail → circuit_breaker.record_failure() викликано."""
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid",
        new=AsyncMock(side_effect=LtsidFetchError("fail")),
    ):
        await _do_emergency_refresh(mock_redis_lock_acquired, circuit_breaker)

    assert circuit_breaker._consecutive_failures == 1


async def test_do_emergency_refresh_releases_lock_even_on_chrome_failure(
    mock_redis_lock_acquired, circuit_breaker
):
    """Lock звільняється через DELETE навіть якщо Chrome fails."""
    with patch(
        "app.pubsub.emergency_refresh.fetch_ltsid",
        new=AsyncMock(side_effect=LtsidFetchError("fail")),
    ):
        await _do_emergency_refresh(mock_redis_lock_acquired, circuit_breaker)

    mock_redis_lock_acquired.delete.assert_called_once_with(REFRESH_LOCK_KEY)


# ---------------------------------------------------------------------------
# Тести: listen_for_refresh_events — CancelledError graceful shutdown
# ---------------------------------------------------------------------------


async def test_listen_graceful_shutdown_on_cancelled_error():
    """CancelledError під час listen → graceful shutdown: unsubscribe + aclose."""
    # listen() має бути async generator (не coroutine) щоб async for міг ітерувати
    async def fake_listen():
        raise asyncio.CancelledError
        yield  # unreachable — робить функцію async generator

    mock_pubsub = AsyncMock()
    mock_pubsub.listen = fake_listen

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    with pytest.raises(asyncio.CancelledError):
        await listen_for_refresh_events(mock_redis)

    mock_pubsub.unsubscribe.assert_called_once()
    mock_pubsub.aclose.assert_called_once()


async def test_listen_reconnects_after_redis_error():
    """При помилці Redis → логується ERROR → reconnect (перевірка через cancel)."""
    call_count = 0

    async def failing_listen():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Redis gone")
        raise asyncio.CancelledError
        yield  # unreachable — робить функцію async generator

    mock_pubsub = AsyncMock()
    mock_pubsub.listen = failing_listen

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    # Мокуємо asyncio.sleep щоб тест не чекав реальні 5 секунд
    with patch("app.pubsub.emergency_refresh.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(asyncio.CancelledError):
            await listen_for_refresh_events(mock_redis)

    # Перевіряємо що було 2 виклики listen (1 fail → reconnect → cancel)
    assert call_count == 2


async def test_listen_skips_non_message_types():
    """Системні повідомлення (type=subscribe) пропускаються."""

    async def fake_listen():
        yield {"type": "subscribe", "channel": b"aetherion:auth:refresh", "data": 1}
        raise asyncio.CancelledError

    mock_pubsub = AsyncMock()
    mock_pubsub.listen = fake_listen

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    with patch(
        "app.pubsub.emergency_refresh._do_emergency_refresh", new=AsyncMock()
    ) as mock_refresh:
        with pytest.raises(asyncio.CancelledError):
            await listen_for_refresh_events(mock_redis)

    mock_refresh.assert_not_called()


async def test_listen_skips_event_when_circuit_open():
    """Коли circuit відкритий — _do_emergency_refresh НЕ викликається."""

    async def fake_listen():
        yield {
            "type": "message",
            "channel": "aetherion:auth:refresh",
            "data": '{"event": "refresh_requested"}',
        }
        raise asyncio.CancelledError

    mock_pubsub = AsyncMock()
    mock_pubsub.listen = fake_listen
    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    # Відкриваємо circuit через патч CircuitBreaker.is_open
    with patch(
        "app.pubsub.emergency_refresh.CircuitBreaker.is_open", return_value=True
    ):
        with patch(
            "app.pubsub.emergency_refresh._do_emergency_refresh", new=AsyncMock()
        ) as mock_refresh:
            with pytest.raises(asyncio.CancelledError):
                await listen_for_refresh_events(mock_redis)

    mock_refresh.assert_not_called()


async def test_listen_calls_do_emergency_refresh_when_message_received():
    """Повідомлення type='message' при закритому circuit → _do_emergency_refresh викликається."""

    async def fake_listen():
        yield {
            "type": "message",
            "channel": "aetherion:auth:refresh",
            "data": '{"event": "refresh_requested"}',
        }
        raise asyncio.CancelledError

    mock_pubsub = AsyncMock()
    mock_pubsub.listen = fake_listen
    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    with patch(
        "app.pubsub.emergency_refresh._do_emergency_refresh", new=AsyncMock()
    ) as mock_refresh:
        with pytest.raises(asyncio.CancelledError):
            await listen_for_refresh_events(mock_redis)

    mock_refresh.assert_called_once()


# ---------------------------------------------------------------------------
# Тести: _wait_for_lock_release — timeout path та fail-closed behavior
# ---------------------------------------------------------------------------


async def test_wait_for_lock_release_logs_warning_on_timeout():
    """Якщо lock не звільняється до дедлайну — логується WARNING 'ltsid_refresh_lock_wait_timeout'."""
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)  # lock завжди зайнятий

    # Встановлюємо нульовий wait_seconds щоб дедлайн настав одразу
    with patch("app.pubsub.emergency_refresh.settings") as mock_settings:
        mock_settings.ltsid_refresh_wait_seconds = 0
        with patch("app.pubsub.emergency_refresh.log") as mock_log:
            from app.pubsub.emergency_refresh import _wait_for_lock_release
            await _wait_for_lock_release(mock_redis)

    mock_log.warning.assert_called_once_with(
        "ltsid_refresh_lock_wait_timeout",
        timeout_seconds=0,
    )


async def test_wait_for_lock_release_redis_error_does_not_call_chrome():
    """Fail-closed: Redis error під час polling → Chrome НЕ запускається.

    При помилці Redis.exists() всередині циклу — lock вважається зайнятим.
    Після закінчення дедлайну логується timeout warning.
    Chrome не викликається — гарантія єдиного refresh зберігається.
    """
    from app.pubsub.emergency_refresh import _wait_for_lock_release

    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(side_effect=ConnectionError("Redis down"))

    with patch("app.pubsub.emergency_refresh.settings") as mock_settings:
        mock_settings.ltsid_refresh_wait_seconds = 0  # дедлайн одразу
        with patch("app.pubsub.emergency_refresh.log") as mock_log:
            await _wait_for_lock_release(mock_redis)

    # Timeout warning — loop вийшов через дедлайн, не через "lock released"
    mock_log.warning.assert_called_with(
        "ltsid_refresh_lock_wait_timeout",
        timeout_seconds=0,
    )


async def test_wait_for_lock_release_redis_error_logs_assuming_held():
    """Fail-closed: Redis error → логується WARNING 'redis_error_during_lock_poll_assuming_held'."""
    from app.pubsub.emergency_refresh import _wait_for_lock_release

    mock_redis = AsyncMock()
    # Перша помилка Redis, потім lock звільняється — щоб loop завершився
    mock_redis.exists = AsyncMock(
        side_effect=[ConnectionError("Redis down"), 0]
    )

    with patch("app.pubsub.emergency_refresh.settings") as mock_settings:
        mock_settings.ltsid_refresh_wait_seconds = 10
        with patch("app.pubsub.emergency_refresh.log") as mock_log:
            with patch("asyncio.sleep", new=AsyncMock()):
                await _wait_for_lock_release(mock_redis)

    # Перший call — warning про Redis error
    mock_log.warning.assert_called_once_with(
        "redis_error_during_lock_poll_assuming_held"
    )


async def test_wait_for_lock_release_redis_error_chrome_not_launched():
    """Fail-closed: Redis error під час dedup polling → _do_emergency_refresh не викликає Chrome.

    Перевіряє що race condition виключено: при помилці Redis під час polling
    fetch_ltsid НЕ викликається — гарантія єдиного refresh зберігається.
    """
    circuit_breaker = CircuitBreaker(threshold=3, pause_seconds=600)

    mock_redis = AsyncMock()
    # SET NX повертає None — lock зайнятий, входимо в dedup wait
    mock_redis.set = AsyncMock(return_value=None)
    # exists кидає виключення — Redis недоступний
    mock_redis.exists = AsyncMock(side_effect=ConnectionError("Redis down"))

    with patch("app.pubsub.emergency_refresh.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)) as mock_fetch:
        with patch("app.pubsub.emergency_refresh.settings") as mock_settings:
            mock_settings.ltsid_refresh_lock_ttl_seconds = 120
            mock_settings.ltsid_refresh_wait_seconds = 0  # дедлайн одразу
            mock_settings.lardi_login = "user"
            mock_settings.lardi_password = "pass"
            mock_settings.chrome_timeout_seconds = 60
            mock_settings.ltsid_ttl_hours = 23
            await _do_emergency_refresh(mock_redis, circuit_breaker)

    # Chrome НЕ викликається — гарантія єдиного refresh
    mock_fetch.assert_not_called()
