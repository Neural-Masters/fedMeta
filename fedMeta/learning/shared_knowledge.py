"""Shared Knowledge manager using Agno's LearnedKnowledgeConfig.

Sets up vector-backed knowledge store with namespace="global" and
PgVector for cross-user knowledge sharing.
"""

from __future__ import annotations

import logging
import hashlib
import uuid
from typing import Any, List, Optional, Dict
import os
from fedMeta.config import get_settings

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class SharedKnowledgeManager:
    """Manages the shared knowledge store for federated learning.

    Wraps Agno's LearnedKnowledgeConfig with a global namespace,
    backed by PgVector for semantic search.  Only sanitized,
    high-confidence learnings are stored here.
    """

    def __init__(
        self,
        namespace: str = "global",
        vector_db: Any = None,
    ) -> None:
        self.settings = get_settings()
        self.namespace = namespace
        self._vector_db = vector_db
        self._knowledge = None
        self._learned_knowledge_config = None

    def initialize(self, embedder: Any = None) -> Any:
        """Initialize the shared Knowledge instance with PgVector.

        Args:
            embedder: Embedding model for vector generation.
                If None, uses OpenAIEmbedder.

        Returns:
            The configured Knowledge instance.
        """
        from agno.knowledge import Knowledge
        from agno.vectordb.pgvector import PgVector, SearchType
        # try:
        #     from agno.knowledge import Knowledge
        #     from agno.vectordb.pgvector import PgVector, SearchType
        # except ImportError as e:
        #     raise ImportError(
        #         "Agno knowledge/vectordb modules not available. "
        #         "Ensure agno[os] is installed."
        #     ) from e

        # Create vector DB if not provided
        if self._vector_db is None:
            try:
                from agno.knowledge.embedder.huggingface import HuggingfaceCustomEmbedder
                from agno.knowledge.embedder.mistral import MistralEmbedder

                # MiniLM produces 384-dim vectors; dimensions must match the
                # PgVector column size or inserts will fail.
                embedder = embedder or MistralEmbedder(
                    id="mistral-embed",
                    dimensions=384,
                    api_key=os.getenv("MISTRAL_API"),
                )
            except ImportError:
                logger.warning(
                    "HuggingFace embedder not available, vector search may not work"
                )
                embedder = None

            self._vector_db = PgVector(
                db_url=self.settings.database_url,
                table_name="agno_learnings",
                schema="public",
                search_type=SearchType.hybrid,
                embedder=embedder,
            )

        self._knowledge = Knowledge(vector_db=self._vector_db)
        logger.info(
            "Shared knowledge initialized with namespace=%s", self.namespace
        )
        return self._knowledge

    def get_learned_knowledge_config(self) -> Any:
        """Get the LearnedKnowledgeConfig for use with LearningMachine.

        Returns:
            LearnedKnowledgeConfig instance.
        """
        try:
            from agno.learn import LearnedKnowledgeConfig, LearningMode
        except ImportError as e:
            raise ImportError(
                "Agno learning module not available. Ensure agno is installed."
            ) from e

        if self._learned_knowledge_config is None:
            self._learned_knowledge_config = LearnedKnowledgeConfig(
                mode=LearningMode.AGENTIC,
                namespace=self.namespace,
                # FedMeta adds a guarded tool that collects explicit consent
                # and a confidence score before any item can be federated.
                agent_can_save=False,
                agent_can_search=True,
            )
        return self._learned_knowledge_config

    def get_knowledge(self) -> Any:
        """Get the Knowledge instance, initializing if necessary."""
        if self._knowledge is None:
            self.initialize()
        assert self._knowledge is not None
        return self._knowledge

    def search_knowledge(
        self,
        query: str,
        limit: int = 5,
    ) -> List[Any]:
        """Search the shared knowledge store via vector similarity.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching knowledge documents.
        """
        knowledge = self.get_knowledge()
        logger.info("Searching shared knowledge for: %s", query)
        try:
            results = self._vector_db.search(query=query, limit=limit)
            return results or []
        except Exception as e:
            logger.error("Knowledge search failed: %s", e)
            return []

    def store_learning(
        self,
        content: str,
        confidence: float = 0.0,
        metadata: Optional[dict] = None,
        name: Optional[str] = None,
    ) -> bool:
        """Store a sanitized learning in the shared knowledge base.

        Learnings below the confidence threshold are rejected.

        Args:
            content: The sanitized learning content.
            confidence: Confidence score (0-1).
            metadata: Optional metadata dictionary.
            name: Optional short title for the learning.

        Returns:
            True if stored successfully.
        """
        if confidence < self.settings.confidence_threshold:
            logger.debug(
                "Learning confidence %.2f below threshold %.2f, skipping",
                confidence,
                self.settings.confidence_threshold,
            )
            return False

        self.get_knowledge()
        payload = dict(metadata or {})
        payload["confidence"] = confidence
        payload["namespace"] = self.namespace

        try:
            from agno.knowledge.document import Document

            content_hash = hashlib.sha256(content.encode()).hexdigest()
            doc = Document(
                content=content,
                name=name or f"learning_{uuid.uuid4().hex[:8]}",
                meta_data=payload,
            )
            self._vector_db.insert(content_hash=content_hash, documents=[doc])
            logger.info("Stored shared learning (confidence=%.2f): %s", confidence, content[:80])
            return True
        except Exception as e:
            logger.error("Failed to store learning: %s", e)
            return False

    def get_all_learnings(
        self,
        limit: int = 100,
        namespace: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Read local Agno knowledge documents, optionally scoped to an owner.

        Returns:
            List of dicts with content, metadata and timestamps.
        """
        self.get_knowledge()
        try:
            import sqlalchemy as sa

            with self._vector_db.db_engine.connect() as conn:
                filters = []
                parameters: Dict[str, Any] = {"limit": limit}
                if namespace is not None:
                    filters.append("meta_data->>'namespace' = :namespace")
                    parameters["namespace"] = namespace
                if namespace == "user":
                    if not user_id:
                        return []
                    filters.append("meta_data->>'user_id' = :user_id")
                    parameters["user_id"] = user_id
                where = f"WHERE {' AND '.join(filters)} " if filters else ""
                result = conn.execute(
                    sa.text(
                        "SELECT id, name, content, meta_data, created_at "
                        f"FROM public.agno_learnings {where}"
                        "ORDER BY created_at DESC LIMIT :limit"
                    ),
                    parameters,
                )
                rows = result.mappings().all()
            documents = [dict(row) for row in rows]
            if namespace is not None:
                documents = [
                    row for row in documents
                    if (row.get("meta_data") or {}).get("namespace") == namespace
                ]
            if namespace == "user":
                if not user_id:
                    return []
                documents = [
                    row for row in documents
                    if (row.get("meta_data") or {}).get("user_id") == user_id
                ]
            return documents[:limit]
        except Exception as e:
            logger.error("Failed to read learnings: %s", e)
            return []
