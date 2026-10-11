"""API endpoint tool registry.

Manages registration, discovery, and retrieval of API endpoints that
can be used as tools by agents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

try:
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from fedMeta.database import APIToolRegistryORM, get_db_manager
    _HAS_SQLALCHEMY = True
except ImportError:
    _HAS_SQLALCHEMY = False

logger = logging.getLogger(__name__)


@dataclass
class APIEndpoint:
    """Represents a registered API endpoint as a tool.

    Attributes:
        name: Unique tool name.
        description: Human-readable description of what the tool does.
        url: The HTTP URL to call.
        method: HTTP method (GET, POST, PUT, DELETE, PATCH).
        headers: Default headers to include.
        input_schema: JSON Schema for input validation.
        output_schema: JSON Schema for expected output.
        tags: Tags for categorization and relevance matching.
        is_active: Whether the tool is currently available.
    """

    name: str
    url: str
    method: str = "GET"
    description: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> APIEndpoint:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            url=data["url"],
            method=data.get("method", "GET"),
            description=data.get("description"),
            headers=data.get("headers", {}),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            tags=data.get("tags", []),
            is_active=data.get("is_active", True),
        )


class APIToolRegistry:
    """Registry for API endpoint tools.

    Provides CRUD operations for API endpoints and relevance-based
    retrieval for tool selection.
    """

    def __init__(self, session: Optional[Session] = None) -> None:
        self._session = session
        self._owns_session = session is None

    @property
    def session(self):
        """Get or create a database session."""
        if not _HAS_SQLALCHEMY:
            raise ImportError("sqlalchemy is required for APIToolRegistry operations")
        if self._session is None:
            self._session = get_db_manager().get_session()
        return self._session

    def register(
        self,
        name: str,
        url: str,
        method: str = "GET",
        description: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> APIEndpoint:
        """Register a new API endpoint tool.

        Args:
            name: Unique tool name.
            url: HTTP URL.
            method: HTTP method.
            description: Tool description.
            headers: Default headers.
            input_schema: JSON Schema for inputs.
            output_schema: JSON Schema for outputs.
            tags: Categorization tags.

        Returns:
            The registered APIEndpoint.

        Raises:
            ValueError: If a tool with this name already exists.
        """
        existing = self.get_tool(name)
        if existing is not None:
            raise ValueError(f"Tool {name!r} already registered")

        orm_tool = APIToolRegistryORM(
            name=name,
            url=url,
            method=method.upper(),
            description=description,
            headers=headers or {},
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            tags=tags or [],
        )
        self.session.add(orm_tool)
        self.session.commit()
        self.session.refresh(orm_tool)
        logger.info("Registered API tool: %s", name)
        return self._orm_to_dataclass(orm_tool)

    def get_tool(self, name: str) -> Optional[APIEndpoint]:
        """Get a registered tool by name.

        Args:
            name: The tool name.

        Returns:
            The APIEndpoint if found, None otherwise.
        """
        stmt = select(APIToolRegistryORM).where(APIToolRegistryORM.name == name)
        result = self.session.execute(stmt).scalar_one_or_none()
        if result is None:
            return None
        return self._orm_to_dataclass(result)

    def list_tools(
        self,
        active_only: bool = True,
        tags: Optional[List[str]] = None,
    ) -> List[APIEndpoint]:
        """List registered tools with optional filtering.

        Args:
            active_only: Only return active tools.
            tags: Filter by tags (tools matching any tag).

        Returns:
            List of matching APIEndpoint objects.
        """
        stmt = select(APIToolRegistryORM)
        if active_only:
            stmt = stmt.where(APIToolRegistryORM.is_active == True)
        results = self.session.execute(stmt).scalars().all()

        tools = [self._orm_to_dataclass(r) for r in results]

        if tags:
            tools = [t for t in tools if any(tag in t.tags for tag in tags)]

        return tools

    def find_relevant_tools(
        self,
        task_context: str,
        limit: int = 5,
    ) -> List[APIEndpoint]:
        """Find tools relevant to a task context.

        Uses simple keyword matching against tool name, description,
        and tags.  In production, this could be replaced with
        embedding-based similarity search.

        Args:
            task_context: Description of the current task.
            limit: Maximum number of tools to return.

        Returns:
            List of relevant APIEndpoint objects, sorted by relevance.
        """
        task_lower = task_context.lower()
        task_words = set(task_lower.split())

        tools = self.list_tools(active_only=True)
        scored_tools: List[tuple] = []

        for tool in tools:
            score = 0
            # Check name match
            if tool.name.lower() in task_lower:
                score += 3
            # Check description match
            if tool.description and tool.description.lower() in task_lower:
                score += 2
            # Check tag matches
            for tag in tool.tags:
                if tag.lower() in task_lower:
                    score += 2
            # Check word overlap
            tool_text = f"{tool.name} {tool.description or ''} {' '.join(tool.tags)}".lower()
            tool_words = set(tool_text.split())
            overlap = len(task_words & tool_words)
            score += overlap

            if score > 0:
                scored_tools.append((score, tool))

        scored_tools.sort(key=lambda x: x[0], reverse=True)
        return [tool for _, tool in scored_tools[:limit]]

    def update_tool(self, name: str, updates: Dict[str, Any]) -> Optional[APIEndpoint]:
        """Update a registered tool.

        Args:
            name: The tool name.
            updates: Fields to update.

        Returns:
            The updated APIEndpoint, or None if not found.
        """
        stmt = select(APIToolRegistryORM).where(APIToolRegistryORM.name == name)
        orm_tool = self.session.execute(stmt).scalar_one_or_none()
        if orm_tool is None:
            return None

        for key, value in updates.items():
            if hasattr(orm_tool, key):
                setattr(orm_tool, key, value)

        self.session.commit()
        self.session.refresh(orm_tool)
        return self._orm_to_dataclass(orm_tool)

    def deactivate_tool(self, name: str) -> bool:
        """Deactivate a tool (soft delete).

        Args:
            name: The tool name.

        Returns:
            True if deactivated, False if not found.
        """
        stmt = select(APIToolRegistryORM).where(APIToolRegistryORM.name == name)
        orm_tool = self.session.execute(stmt).scalar_one_or_none()
        if orm_tool is None:
            return False

        orm_tool.is_active = False
        self.session.commit()
        return True

    def delete_tool(self, name: str) -> bool:
        """Permanently delete a tool.

        Args:
            name: The tool name.

        Returns:
            True if deleted, False if not found.
        """
        stmt = select(APIToolRegistryORM).where(APIToolRegistryORM.name == name)
        orm_tool = self.session.execute(stmt).scalar_one_or_none()
        if orm_tool is None:
            return False

        self.session.delete(orm_tool)
        self.session.commit()
        return True

    def close(self) -> None:
        """Close the session if owned by this manager."""
        if self._owns_session and self._session is not None:
            self._session.close()
            self._session = None

    @staticmethod
    def _orm_to_dataclass(orm: APIToolRegistryORM) -> APIEndpoint:
        """Convert ORM to dataclass."""
        return APIEndpoint(
            name=orm.name,
            url=orm.url,
            method=orm.method,
            description=orm.description,
            headers=orm.headers or {},
            input_schema=orm.input_schema or {},
            output_schema=orm.output_schema or {},
            tags=orm.tags or [],
            is_active=orm.is_active,
        )
