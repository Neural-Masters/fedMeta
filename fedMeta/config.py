"""Environment-based configuration for FedMeta.

Supports dev, staging, and production environments via the ``FEDMETA_ENV``
environment variable.  Defaults to ``dev``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass


class Settings:
    """Runtime configuration for FedMeta."""

    def __init__(self) -> None:
        self.env: str = os.getenv("FEDMETA_ENV", "dev")
        self.debug: bool = os.getenv("FEDMETA_DEBUG", "true").lower() == "true"

        # Database
        self.database_url: str = os.getenv(
            "FEDMETA_DATABASE_URL",
            "sqlite:///fedmeta.db",
        )

        # Federated server
        self.server_url: str = os.getenv(
            "FEDMETA_SERVER_URL",
            "http://localhost:8000",
        )
        self.server_ws_url: str = os.getenv(
            "FEDMETA_SERVER_WS_URL",
            "ws://localhost:8000",
        )

        # Sync settings
        self.sync_interval_seconds: int = int(
            os.getenv("FEDMETA_SYNC_INTERVAL", "30")
        )
        self.confidence_threshold: float = float(
            os.getenv("FEDMETA_CONFIDENCE_THRESHOLD", "0.85")
        )
        self.federated_listener_enabled: bool = (
            os.getenv("FEDMETA_FEDERATED_LISTENER_ENABLED", "true").lower() == "true"
        )

        # Vector store
        self.pgvector_dimensions: int = int(
            os.getenv("FEDMETA_PGVECTOR_DIMENSIONS", "1536")
        )

        # Logging
        self.log_level: str = os.getenv("FEDMETA_LOG_LEVEL", "INFO")

        # LLM settings — from .env
        self.model: str = os.getenv("MODEL", "openai:gpt-4o")
        self.open_code_api: str = os.getenv("OPEN_CODE_API", "")
        self.open_code_uri: str = os.getenv("OPEN_CODE_URI", "")
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    def __repr__(self) -> str:
        return (
            f"Settings(env={self.env!r}, debug={self.debug}, "
            f"database_url={self.database_url!r}, "
            f"server_url={self.server_url!r}, "
            f"model={self.model!r})"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
