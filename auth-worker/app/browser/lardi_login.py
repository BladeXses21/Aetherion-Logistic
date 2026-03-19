"""lardi_login.py — Автентифікація на Lardi-Trans через Chrome.

Використовує undetected-chromedriver для обходу Cloudflare Bot Management.
Відкриває headless браузер, заповнює форму входу та витягує LTSID cookie.

Lardi-Trans захищений Cloudflare, тому пряме HTTP-логінення неможливе —
потрібен справжній браузер із валідним CF clearance token.
"""
from __future__ import annotations

import asyncio
import contextlib
import time

import structlog
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.core.errors import ChromeStartupError, LtsidFetchError

log = structlog.get_logger()

# URL захищеної сторінки — при відсутності сесії редіректить на форму логіну
_LARDI_ENTRY_URL = "https://lardi-trans.com/log/search/gruz/"

# Назви полів форми логіну (атрибут name у HTML)
_FIELD_LOGIN = "login"
_FIELD_PASSWORD = "password"


async def fetch_ltsid(login: str, password: str, timeout_seconds: int) -> str:
    """Отримує LTSID cookie через автоматичний вхід у браузері Lardi-Trans.

    Запускає Chrome у headless-режимі в окремому executor-потоці
    (selenium є синхронною бібліотекою).

    Args:
        login: Email або логін облікового запису Lardi-Trans.
        password: Пароль облікового запису.
        timeout_seconds: Максимальний час очікування на cookie (секунди).

    Returns:
        Рядок значення LTSID cookie (непорожній).

    Raises:
        ChromeStartupError: Якщо Chrome не вдалось запустити.
        LtsidFetchError: Якщо вхід провалився або LTSID не з'явився.

    Example:
        >>> ltsid = await fetch_ltsid("user@example.com", "secret", timeout_seconds=60)
        >>> len(ltsid) > 0
        True
    """
    loop = asyncio.get_event_loop()
    try:
        ltsid = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_fetch, login, password, timeout_seconds),
            timeout=timeout_seconds + 15,  # додатковий буфер для старту Chrome
        )
    except asyncio.TimeoutError as exc:
        raise LtsidFetchError(
            f"Chrome login exceeded total timeout ({timeout_seconds + 15}s)"
        ) from exc
    return ltsid


def _sync_fetch(login: str, password: str, timeout: int) -> str:
    """Синхронна реалізація логіну — виконується у ThreadPoolExecutor.

    Args:
        login: Email або логін.
        password: Пароль (НЕ логується жодним чином).
        timeout: Максимальний час очікування cookie у секундах.

    Returns:
        Значення LTSID cookie.

    Raises:
        ChromeStartupError: Якщо ініціалізація Chrome завершилась помилкою.
        LtsidFetchError: Якщо LTSID не отримано за відведений час.
    """
    # Імпорт тут, щоб уникнути помилок імпорту у тестах без Chrome
    try:
        import undetected_chromedriver as uc
    except ImportError as exc:
        raise ChromeStartupError("undetected-chromedriver not installed") from exc

    opts = uc.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")

    try:
        driver = uc.Chrome(options=opts)
    except WebDriverException as exc:
        raise ChromeStartupError(f"Chrome failed to start: {exc}") from exc
    except Exception as exc:
        raise ChromeStartupError(f"Unexpected Chrome init error: {exc}") from exc

    try:
        return _do_login(driver, login, password, timeout)
    finally:
        with contextlib.suppress(Exception):
            driver.quit()


def _do_login(driver, login: str, password: str, timeout: int) -> str:
    """Виконує процес логіну: відкриває сторінку, заповнює форму, чекає LTSID.

    Також обробляє модальне вікно "Занадто багато активних сесій",
    якщо воно з'являється після входу.

    Args:
        driver: Екземпляр undetected_chromedriver.Chrome.
        login: Логін (НЕ логується).
        password: Пароль (НЕ логується).
        timeout: Максимальний час очікування у секундах.

    Returns:
        Значення LTSID cookie.

    Raises:
        LtsidFetchError: Якщо форму не знайдено або LTSID не з'явився.
    """
    log.info("lardi_browser_login_start", url=_LARDI_ENTRY_URL)
    driver.get(_LARDI_ENTRY_URL)

    wait = WebDriverWait(driver, timeout)

    try:
        login_field = wait.until(
            EC.presence_of_element_located((By.NAME, _FIELD_LOGIN))
        )
    except Exception as exc:
        raise LtsidFetchError(
            "Login form not found — Lardi may have changed page structure"
        ) from exc

    try:
        password_field = driver.find_element(By.NAME, _FIELD_PASSWORD)
    except Exception as exc:
        raise LtsidFetchError("Password field not found on login form") from exc

    login_field.clear()
    login_field.send_keys(login)
    password_field.clear()
    password_field.send_keys(password)
    password_field.submit()

    log.info("lardi_browser_form_submitted")

    # Обробка модалки "Занадто багато активних сесій"
    _dismiss_session_limit_modal(driver, timeout=min(timeout, 10))

    # Очікуємо появу LTSID cookie
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        if cookies.get("LTSID"):
            log.info("lardi_browser_ltsid_acquired")
            return cookies["LTSID"]
        time.sleep(0.5)

    raise LtsidFetchError("LTSID cookie not found after form submission — login may have failed")


def _dismiss_session_limit_modal(driver, timeout: int) -> None:
    """Закриває модальне вікно ліміту активних сесій, якщо воно з'явилось.

    Lardi показує модалку зі списком активних сесій, якщо їх забагато.
    Натискаємо кнопку "Продовжити" (Continue), щоб пройти далі.

    Args:
        driver: Екземпляр браузера.
        timeout: Максимальний час очікування кнопки у секундах.
    """
    try:
        # Шукаємо кнопку продовження в модалці (може бути "Продовжити" або "Continue")
        continue_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(., 'родовжити') or contains(., 'ontinue')]")
            )
        )
        continue_btn.click()
        log.info("lardi_session_limit_modal_dismissed")
    except Exception:
        # Модалки немає — це нормально, пропускаємо
        pass
