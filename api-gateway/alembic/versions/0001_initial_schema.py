"""Initial schema: users, workspaces, workspace_users, chats, messages, ua_cities

Revision ID: 0001
Revises:
Create Date: 2026-03-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Extensions ─────────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── workspaces ─────────────────────────────────────────────────────────────
    op.create_table(
        "workspaces",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_workspaces_name", "workspaces", ["name"], unique=True)

    # ── workspace_users ────────────────────────────────────────────────────────
    op.create_table(
        "workspace_users",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_workspace_users_workspace_id", "workspace_users", ["workspace_id"]
    )
    op.create_index("ix_workspace_users_user_id", "workspace_users", ["user_id"])

    # ── chats ──────────────────────────────────────────────────────────────────
    op.create_table(
        "chats",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "title", sa.String(255), nullable=False, server_default="New chat"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_chats_workspace_id", "chats", ["workspace_id"])
    op.create_index("ix_chats_user_id", "chats", ["user_id"])

    # ── messages ───────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "chat_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="complete"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_messages_chat_id", "messages", ["chat_id"])

    # ── ua_cities ──────────────────────────────────────────────────────────────
    op.create_table(
        "ua_cities",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name_ua", sa.String(150), nullable=False),
        sa.Column("region_name", sa.String(100), nullable=True),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("lardi_town_id", sa.Integer, nullable=True),
        sa.Column(
            "source", sa.String(30), nullable=False, server_default="nominatim"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_ua_cities_name_ua", "ua_cities", ["name_ua"])
    op.create_index(
        "ix_ua_cities_lardi_town_id", "ua_cities", ["lardi_town_id"], unique=True
    )
    # GIN trigram index for fuzzy city name matching (used in Story 4.1 geo_resolver)
    op.execute(
        "CREATE INDEX ix_ua_cities_name_trgm ON ua_cities "
        "USING gin(name_ua gin_trgm_ops)"
    )

    # pgvector: optional — only added if extension is available in this Postgres instance.
    # PL/pgSQL DO block handles the exception at SQL level so the transaction stays healthy.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                CREATE EXTENSION IF NOT EXISTS vector;
                ALTER TABLE ua_cities ADD COLUMN IF NOT EXISTS embedding vector(384);
                CREATE INDEX IF NOT EXISTS ix_ua_cities_embedding_hnsw ON ua_cities
                    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
            EXCEPTION WHEN OTHERS THEN
                NULL;  -- pgvector not installed; embedding column deferred
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("chats")
    op.drop_table("workspace_users")
    op.drop_table("workspaces")
    op.drop_table("users")
    op.drop_table("ua_cities")
