"""Add is_active and role fields to users (Epic 9.1 — JWT auth)

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Додаємо is_active — whitelist через soft-delete (False = заблокований)
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    # Додаємо role — "user" | "admin"
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
    op.drop_column("users", "is_active")
