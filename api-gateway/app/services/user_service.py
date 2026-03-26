"""
user_service.py — Сервіс для управління користувачами (Epic 9.1).

Надає операції:
  - get_by_email: пошук користувача по email для логіну
  - create_user: створення нового користувача (для адмін ендпоінта)
  - deactivate_user: блокування (soft-delete через is_active=False)
  - list_users: перелік всіх користувачів для адмін панелі
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models.user import User


class UserService:
    """
    Сервісний шар для операцій з користувачами.

    Всі методи приймають async db сесію та повертають ORM об'єкти.
    """

    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        """
        Знаходить користувача по email адресі.

        Args:
            db: Async сесія БД.
            email: Email для пошуку (регістронезалежний через lower).

        Returns:
            User якщо знайдено, None — якщо не існує.
        """
        result = await db.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        role: str = "user",
    ) -> User:
        """
        Створює нового активного користувача з хешованим паролем.

        Використовується адмін ендпоінтом POST /api/v1/admin/users.
        Email автоматично нормалізується до нижнього регістру.

        Args:
            db: Async сесія БД.
            email: Email нового користувача.
            password: Відкритий пароль (буде захешований bcrypt).
            role: Роль — "user" або "admin" (за замовчуванням "user").

        Returns:
            Новий User об'єкт (незакомічений, потребує db.commit()).

        Raises:
            sqlalchemy.exc.IntegrityError: Якщо email вже існує.
        """
        user = User(
            id=uuid.uuid4(),
            email=email.lower().strip(),
            hashed_password=hash_password(password),
            is_active=True,
            role=role,
        )
        db.add(user)
        await db.flush()  # отримуємо id без commit
        return user

    async def deactivate_user(self, db: AsyncSession, user_id: uuid.UUID) -> User | None:
        """
        Деактивує користувача (soft-delete — встановлює is_active=False).

        Args:
            db: Async сесія БД.
            user_id: UUID користувача для деактивації.

        Returns:
            User з is_active=False або None якщо не знайдено.
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_active = False
            await db.flush()
        return user

    async def list_users(self, db: AsyncSession) -> list[User]:
        """
        Повертає список всіх користувачів (для адмін панелі).

        Args:
            db: Async сесія БД.

        Returns:
            Список User об'єктів відсортованих за датою створення.
        """
        result = await db.execute(select(User).order_by(User.created_at))
        return list(result.scalars().all())


user_service = UserService()
