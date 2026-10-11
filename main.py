"""FedMeta entry point.

Initializes the database, builds the meta-agent, and starts the
federated learning server.
"""

from __future__ import annotations

import logging

from fedMeta.agent_builder import build_meta_agent
from fedMeta.config import get_settings
from fedMeta.database import get_db_manager

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for FedMeta."""
    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting FedMeta (env=%s)", settings.env)

    # Initialize database
    db_manager = get_db_manager()
    db_manager.create_tables()
    logger.info("Database initialized: %s", settings.database_url)

    # Build the meta-agent (model will be configured by the caller)
    # agent = build_meta_agent(model=your_model_instance)
    logger.info("FedMeta initialized successfully")

    # To start the federated learning server:
    # from server.main import main as server_main
    # server_main()


if __name__ == "__main__":
    main()
