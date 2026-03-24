"""
session.py — Асинхронне підключення до PostgreSQL для agent-service.

Використовується виключно в geo_resolver.py для читання таблиці ua_cities.
Не включає ORM моделей — тільки сирі SQL-запити через text().

Підключення до тієї ж БД що й api-gateway (спільна схема).
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Асинхронний движок SQLAlchemy для читання ua_cities
engine = create_async_engine(
    settings.postgres_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

# Фабрика сесій для geo_resolver
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency Injection провайдер асинхронної сесії БД.

    Автоматично коммітить при успіху або відкочує при виключенні.
    Призначений для використання в geo_resolver та інших сервісах agent-service
    що потребують доступу до PostgreSQL.

    Yields:
        AsyncSession — активна сесія для виконання запитів.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
