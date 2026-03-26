"""
security.py — Утиліти для JWT автентифікації та хешування паролів (Epic 9.1).

Містить:
  - hash_password / verify_password: bcrypt через passlib
  - create_access_token: видача JWT токена після успішного логіну
  - decode_access_token: перевірка та декодування JWT

Алгоритм: HS256 (HMAC-SHA256) — стандартний для stateless сесій.
Payload JWT: {"sub": "<user_id_str>", "email": "<email>", "role": "<role>", "exp": <timestamp>}
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Контекст bcrypt для хешування паролів
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Хешує пароль через bcrypt.

    Args:
        plain_password: Відкритий текст пароля.

    Returns:
        bcrypt хеш для збереження у БД.
    """
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Перевіряє відповідність відкритого пароля bcrypt хешу.

    Args:
        plain_password: Введений користувачем пароль.
        hashed_password: Збережений у БД bcrypt хеш.

    Returns:
        True якщо пароль відповідає хешу, False — інакше.
    """
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, email: str, role: str) -> str:
    """
    Генерує підписаний JWT access token.

    Payload містить:
        - sub: UUID користувача (рядок)
        - email: email користувача
        - role: "user" або "admin"
        - exp: час закінчення токена (UTC)

    Args:
        user_id: UUID користувача (рядок).
        email: Email користувача.
        role: Роль користувача ("user" або "admin").

    Returns:
        Підписаний JWT рядок (Bearer token).

    Приклад:
        token = create_access_token("uuid-...", "user@example.com", "admin")
    """
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """
    Декодує та перевіряє JWT токен.

    Перевіряє підпис та термін дії (exp).
    При будь-якій помилці (expired, invalid signature, malformed) — повертає None.

    Args:
        token: JWT рядок з Authorization: Bearer заголовка.

    Returns:
        dict з payload (sub, email, role, exp) або None при невалідному токені.
    """
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None
