"""
chat_service.py — Сервіс управління чатами та повідомленнями (Story 4.4).

Забезпечує CRUD операції з таблицями chats та messages через SQLAlchemy async.
Всі методи — async. Транзакції керуються на рівні сесії.

Відповідальність:
  - Створення чатів
  - Збереження повідомлень користувача
  - Збереження placeholder повідомлення асистента (status="streaming")
  - Оновлення статусу/контенту після завершення стріму
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.message import Message

log = structlog.get_logger()


class ChatService:
    """
    Сервіс для роботи з чатами та повідомленнями.

    Всі операції виконуються через переданий AsyncSession.
    Не зберігає стан між викликами — stateless service.
    """

    async def create_chat(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str = "Новий пошук",
    ) -> Chat:
        """
        Створює новий чат в базі даних.

        Автоматично генерує UUID для нового чату.
        Перед збереженням забезпечує що workspace та user існують
        (для MVP — використовуються stub записи, які auto-created якщо потрібно).

        Args:
            db: Активна асинхронна сесія PostgreSQL.
            workspace_id: UUID робочого простору.
            user_id: UUID користувача.
            title: Назва чату.

        Returns:
            Збережений об'єкт Chat.
        """
        await self._ensure_workspace_and_user(db, workspace_id, user_id)

        chat = Chat(
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
        )
        db.add(chat)
        await db.flush()  # отримуємо id без commit
        await db.refresh(chat)

        log.info(
            "chat_created",
            chat_id=str(chat.id),
            workspace_id=str(workspace_id),
        )
        return chat

    async def save_user_message(
        self,
        db: AsyncSession,
        chat_id: uuid.UUID,
        content: str,
    ) -> Message:
        """
        Зберігає повідомлення користувача з status="complete".

        Args:
            db: Активна асинхронна сесія PostgreSQL.
            chat_id: UUID чату.
            content: Текст повідомлення.

        Returns:
            Збережений об'єкт Message.
        """
        message = Message(
            chat_id=chat_id,
            role="user",
            content=content,
            status="complete",
        )
        db.add(message)
        await db.flush()
        await db.refresh(message)

        log.debug("user_message_saved", chat_id=str(chat_id), message_id=str(message.id))
        return message

    async def create_assistant_placeholder(
        self,
        db: AsyncSession,
        chat_id: uuid.UUID,
    ) -> Message:
        """
        Створює placeholder повідомлення асистента зі status="streaming".

        Зберігається перед початком SSE стріму щоб клієнт міг відстежити
        статус відповіді. Після завершення стріму оновлюється через
        update_assistant_message().

        Args:
            db: Активна асинхронна сесія PostgreSQL.
            chat_id: UUID чату.

        Returns:
            Збережений Message з role="assistant", status="streaming".
        """
        message = Message(
            chat_id=chat_id,
            role="assistant",
            content="",  # порожній до завершення стріму
            status="streaming",
        )
        db.add(message)
        await db.flush()
        await db.refresh(message)

        log.debug(
            "assistant_placeholder_created",
            chat_id=str(chat_id),
            message_id=str(message.id),
        )
        return message

    async def update_assistant_message(
        self,
        db: AsyncSession,
        message_id: uuid.UUID,
        content: str,
        status: str,
    ) -> None:
        """
        Оновлює контент та статус повідомлення асистента після завершення стріму.

        Статуси:
          "complete"   — стрім завершився успішно, весь контент збережено
          "incomplete" — з'єднання перервано до завершення, збережено частковий контент

        Args:
            db: Активна асинхронна сесія PostgreSQL.
            message_id: UUID повідомлення для оновлення.
            content: Повний або частковий текст відповіді асистента.
            status: Новий статус ("complete" або "incomplete").
        """
        result = await db.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one_or_none()

        if message:
            message.content = content
            message.status = status
            await db.flush()
            log.debug(
                "assistant_message_updated",
                message_id=str(message_id),
                status=status,
                content_len=len(content),
            )

    async def get_chat_history(
        self,
        db: AsyncSession,
        chat_id: uuid.UUID,
        limit: int = 20,
    ) -> list[Message]:
        """
        Отримує останні повідомлення чату для передачі в контекст агента.

        Повертає повідомлення у хронологічному порядку (від старіших до новіших).
        Фільтрує тільки complete/incomplete (пропускає streaming placeholder).

        Args:
            db: Активна асинхронна сесія PostgreSQL.
            chat_id: UUID чату.
            limit: Максимальна кількість повідомлень (за замовчуванням 20).

        Returns:
            Список Message у хронологічному порядку.
        """
        result = await db.execute(
            select(Message)
            .where(
                Message.chat_id == chat_id,
                Message.status.in_(["complete", "incomplete"]),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = result.scalars().all()
        return list(reversed(messages))  # від старіших до новіших

    async def _ensure_workspace_and_user(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """
        Забезпечує існування workspace та user записів у БД (для MVP stub).

        Для MVP створює мінімальні записи якщо вони ще не існують.
        В Phase 2 буде замінено повноцінним auth middleware.

        Args:
            db: Активна асинхронна сесія PostgreSQL.
            workspace_id: UUID робочого простору.
            user_id: UUID користувача.
        """
        from app.db.models.user import User
        from app.db.models.workspace import Workspace
        from app.db.models.workspace_user import WorkspaceUser

        # Перевіряємо чи існує workspace
        ws_result = await db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        if not ws_result.scalar_one_or_none():
            workspace = Workspace(id=workspace_id, name=f"workspace-{str(workspace_id)[:8]}")
            db.add(workspace)
            await db.flush()

        # Перевіряємо чи існує user
        user_result = await db.execute(select(User).where(User.id == user_id))
        if not user_result.scalar_one_or_none():
            user = User(
                id=user_id,
                email=f"user-{str(user_id)[:8]}@stub.aetherion.local",
            )
            db.add(user)
            await db.flush()

        # Перевіряємо чи існує workspace_user
        wu_result = await db.execute(
            select(WorkspaceUser).where(
                WorkspaceUser.workspace_id == workspace_id,
                WorkspaceUser.user_id == user_id,
            )
        )
        if not wu_result.scalar_one_or_none():
            wu = WorkspaceUser(
                workspace_id=workspace_id,
                user_id=user_id,
                role="owner",
            )
            db.add(wu)
            await db.flush()


# Singleton екземпляр
chat_service = ChatService()
