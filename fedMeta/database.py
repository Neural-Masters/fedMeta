"""Database connection and ORM models for FedMeta.

Uses SQLAlchemy with support for both PostgreSQL (production) and
SQLite (development fallback).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect as sa_inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from fedMeta.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class UserProfileORM(Base):
    """Database model for user profiles."""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expertise_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    communication_style: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    preferred_format: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    domains: Mapped[List[str]] = mapped_column(JSON, default=list)
    custom_rules: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class UserAccountORM(Base):
    """Local username/password account; only a salted password hash is stored."""

    __tablename__ = "user_accounts"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AuthSessionORM(Base):
    """Opaque, expiring bearer sessions stored as token hashes."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_accounts.user_id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class APIToolRegistryORM(Base):
    """Database model for registered API endpoint tools."""

    __tablename__ = "api_tool_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    owner_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET")
    headers: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict)
    input_schema: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    output_schema: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", name="uq_api_tool_registry_owner_name"),
    )


class SharedLearningORM(Base):
    """Database model for shared/federated learnings."""

    __tablename__ = "shared_learnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learning_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(255), default="global")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_user_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    learning_metadata: Mapped[Dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DecisionLogORM(Base):
    """Database model for agent decision logs."""

    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alternatives: Mapped[List[str]] = mapped_column(JSON, default=list)
    outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class FederatedSyncStateORM(Base):
    """Database model for federated sync state tracking."""

    __tablename__ = "federated_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_pushed_count: Mapped[int] = mapped_column(Integer, default=0)
    last_pulled_count: Mapped[int] = mapped_column(Integer, default=0)
    sync_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class FederatedOutboxORM(Base):
    """Locally queued, sanitized learnings awaiting central acknowledgement."""

    __tablename__ = "federated_learning_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    learning_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    learning_metadata: Mapped[Dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FederatedReceiptORM(Base):
    """Tracks central learnings already applied to a user's local Agno store."""

    __tablename__ = "federated_learning_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    learning_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    __table_args__ = (
        UniqueConstraint("user_id", "learning_id", name="uq_federated_receipt_user_learning"),
    )


class DatabaseManager:
    """Manages database connections and provides CRUD operations.

    Supports PostgreSQL (with pgvector) for production and SQLite
    for development.
    """

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.settings = get_settings()
        self.database_url = database_url or self.settings.database_url
        self._engine = None
        self._session_factory = None

    @property
    def engine(self):
        """Lazy-initialize the SQLAlchemy engine."""
        if self._engine is None:
            connect_args = {}
            if self.database_url.startswith("sqlite"):
                connect_args["check_same_thread"] = False
            self._engine = create_engine(
                self.database_url,
                echo=self.settings.debug,
                connect_args=connect_args,
            )
        return self._engine

    @property
    def session_factory(self):
        """Lazy-initialize the session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine)
        return self._session_factory

    def create_tables(self) -> None:
        """Create tables and safely migrate existing tool registry ownership."""
        Base.metadata.create_all(self.engine)
        self._migrate_tool_ownership()
        logger.info("Database tables created successfully")

    def _migrate_tool_ownership(self) -> None:
        """Add per-user tool ownership and replace the old globally-unique name index."""
        inspector = sa_inspect(self.engine)
        if not inspector.has_table("api_tool_registry"):
            return

        columns = {column["name"] for column in inspector.get_columns("api_tool_registry")}
        with self.engine.begin() as connection:
            if "owner_user_id" not in columns:
                connection.execute(
                    text("ALTER TABLE api_tool_registry ADD COLUMN owner_user_id VARCHAR(36)")
                )

            # Prior schema used a global unique index on tool name. Remove only
            # that specific index; legacy rows stay unowned and hidden from accounts.
            refreshed = sa_inspect(connection)
            for index in refreshed.get_indexes("api_tool_registry"):
                if index.get("unique") and index.get("column_names") == ["name"]:
                    index_name = index["name"].replace('"', '""')
                    connection.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))

            unique_pairs = [
                tuple(constraint.get("column_names") or [])
                for constraint in refreshed.get_unique_constraints("api_tool_registry")
            ]
            indexes = refreshed.get_indexes("api_tool_registry")
            has_owner_name = ("owner_user_id", "name") in unique_pairs or any(
                index.get("unique")
                and tuple(index.get("column_names") or []) == ("owner_user_id", "name")
                for index in indexes
            )
            if not has_owner_name:
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "uq_api_tool_registry_owner_name "
                        "ON api_tool_registry (owner_user_id, name)"
                    )
                )

    def get_session(self):
        """Get a new database session."""
        return self.session_factory()

    def is_postgres(self) -> bool:
        """Return True if connected to PostgreSQL."""
        return self.database_url.startswith("postgresql")

    def close(self) -> None:
        """Close the database connection."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None


# Module-level singleton
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get or create the global DatabaseManager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
