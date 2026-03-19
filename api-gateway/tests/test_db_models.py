"""Offline tests for ORM model structure and DB session setup."""


def test_all_models_importable():
    from app.db.models import Chat, City, Message, User, Workspace, WorkspaceUser

    assert User.__tablename__ == "users"
    assert Workspace.__tablename__ == "workspaces"
    assert WorkspaceUser.__tablename__ == "workspace_users"
    assert Chat.__tablename__ == "chats"
    assert Message.__tablename__ == "messages"
    assert City.__tablename__ == "ua_cities"


def test_base_and_session_importable():
    from app.db.base import Base, TimestampMixin  # noqa: F401
    from app.db.session import engine, get_db  # noqa: F401

    assert engine is not None


def test_base_metadata_contains_all_tables():
    import app.db.models  # noqa: F401 — registers all models
    from app.db.base import Base

    table_names = set(Base.metadata.tables.keys())
    expected = {"users", "workspaces", "workspace_users", "chats", "messages", "ua_cities"}
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"


def test_user_model_columns():
    from app.db.models.user import User

    cols = {c.name for c in User.__table__.columns}
    assert {"id", "email", "hashed_password", "created_at"}.issubset(cols)


def test_workspace_model_columns():
    from app.db.models.workspace import Workspace

    cols = {c.name for c in Workspace.__table__.columns}
    assert {"id", "name", "created_at"}.issubset(cols)
    # workspaces must NOT have owner_id — ownership is via workspace_users
    assert "owner_id" not in cols


def test_workspace_user_composite_pk():
    from app.db.models.workspace_user import WorkspaceUser

    pk_cols = {c.name for c in WorkspaceUser.__table__.primary_key.columns}
    assert pk_cols == {"workspace_id", "user_id"}


def test_chat_has_workspace_and_user_fk():
    from app.db.models.chat import Chat

    fk_targets = {fk.target_fullname for fk in Chat.__table__.foreign_keys}
    assert "workspaces.id" in fk_targets
    assert "users.id" in fk_targets


def test_message_has_chat_fk():
    from app.db.models.message import Message

    fk_targets = {fk.target_fullname for fk in Message.__table__.foreign_keys}
    assert "chats.id" in fk_targets


def test_message_status_column_exists():
    from app.db.models.message import Message

    cols = {c.name for c in Message.__table__.columns}
    assert "status" in cols
    assert "role" in cols
    assert "content" in cols


def test_city_uses_serial_pk():
    from app.db.models.city import City
    from sqlalchemy import Integer

    pk_col = City.__table__.c["id"]
    assert isinstance(pk_col.type, Integer)
    assert pk_col.autoincrement is True or pk_col.autoincrement == "auto"


def test_city_lardi_town_id_is_unique():
    from app.db.models.city import City

    lardi_col = City.__table__.c["lardi_town_id"]
    # unique constraint exists (via Index or column-level)
    assert lardi_col.unique is True or any(
        idx.unique for idx in City.__table__.indexes
        if any(c.name == "lardi_town_id" for c in idx.columns)
    )
