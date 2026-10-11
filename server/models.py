"""Pydantic models for the FedMeta federated learning server."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FederatedLearningPayload(BaseModel):
    """One high-confidence anonymous insight; deliberately excludes user IDs."""

    model_config = ConfigDict(extra="forbid")

    learning_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=10000)
    confidence: float = Field(ge=0.0, le=1.0)
    namespace: str = Field(default="global", pattern="^global$")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PushLearningRequest(BaseModel):
    """Request model contains no user/device identifier."""

    model_config = ConfigDict(extra="forbid")

    learnings: List[FederatedLearningPayload] = Field(default_factory=list, max_length=100)


class PushLearningResponse(BaseModel):
    """Response model for push operation."""

    status: str = Field(description="Status of the operation")
    pushed: int = Field(description="Number of learnings accepted")
    duplicates: int = 0
    rejected: int = 0
    message: Optional[str] = Field(default=None)


class PullLearningRequest(BaseModel):
    """Request model for pulling global learnings."""

    namespace: str = Field(default="global")
    limit: int = Field(default=10, ge=1, le=100)
    since: Optional[datetime] = Field(default=None)
    offset: int = Field(default=0, ge=0)


class PullLearningResponse(BaseModel):
    """Response model for pull operation."""

    status: str
    learnings: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class KnowledgeQueryRequest(BaseModel):
    """Request model for querying global knowledge."""

    query: str = Field(min_length=1, max_length=1000)
    namespace: str = Field(default="global")
    limit: int = Field(default=5, ge=1, le=50)


class KnowledgeQueryResponse(BaseModel):
    """Response model for knowledge query."""

    status: str
    results: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class LearningEntry(BaseModel):
    """A single learning entry stored on the server."""

    learning_id: str
    title: str = "Shared learning"
    namespace: str = "global"
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WebSocketMessage(BaseModel):
    """WebSocket message format."""

    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
