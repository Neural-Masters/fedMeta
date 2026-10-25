"""FastAPI server for FedMeta.

Provides endpoints for:
- User profile management
- API tool registry
- Learning dashboard
- Agent chat
- Federated learning sync
"""

from __future__ import annotations

import json
import logging
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import hmac
import re
from typing import Any, Dict, List, Optional, Set

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from fedMeta.config import get_settings
from fedMeta.database import (
    AuthSessionORM,
    SharedLearningORM,
    UserAccountORM,
    UserProfileORM,
    get_db_manager,
)
from fedMeta.auth import create_session_token, hash_password, hash_session_token, normalize_username, verify_password
from fedMeta.federated.sanitizer import LearningSanitizer

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="FedMeta Server",
    description="Adaptive Profile Framework with Federated Learning",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Live WebSocket subscribers; durable learning records live in PostgreSQL.
connected_websockets: Set[WebSocket] = set()
sanitizer = LearningSanitizer()
federation_listener_task: Optional[asyncio.Task] = None


async def _broadcast(message: Dict[str, Any]) -> None:
    """Broadcast a global-learning event and prune disconnected clients."""
    disconnected: Set[WebSocket] = set()
    for client in tuple(connected_websockets):
        try:
            await client.send_json(message)
        except Exception:
            disconnected.add(client)
    connected_websockets.difference_update(disconnected)


# --- Pydantic Models ---

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    expertise_level: Optional[str] = None
    communication_style: Optional[str] = None
    preferred_format: Optional[str] = None
    domains: Optional[List[str]] = None
    custom_rules: Optional[Dict[str, Any]] = None


class ToolRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    url: str
    method: str = "GET"
    description: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class ToolUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    response: str
    user_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CredentialsRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=10, max_length=128)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    username: str
    token_hash: str


def get_current_user(authorization: Optional[str] = Header(default=None)) -> AuthenticatedUser:
    """Validate a bearer session token and resolve its account identity."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue", headers={"WWW-Authenticate": "Bearer"})

    token = authorization[7:].strip()
    if not token or len(token) > 256:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    token_hash = hash_session_token(token)
    session = get_db_manager().get_session()
    try:
        result = session.execute(
            select(AuthSessionORM, UserAccountORM)
            .join(UserAccountORM, AuthSessionORM.user_id == UserAccountORM.user_id)
            .where(
                AuthSessionORM.token_hash == token_hash,
                AuthSessionORM.revoked_at.is_(None),
            )
        ).first()
        if result is None:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        auth_session, account = result
        expires_at = auth_session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        return AuthenticatedUser(
            user_id=account.user_id,
            username=account.username,
            token_hash=token_hash,
        )
    finally:
        session.close()


def require_path_user(
    user_id: str,
    current: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Ensure a caller cannot read or mutate another account's path-scoped data."""
    if not hmac.compare_digest(user_id, current.user_id):
        raise HTTPException(status_code=403, detail="You cannot access another account's data")
    return current


def _issue_session(session: Any, user_id: str) -> tuple[str, datetime]:
    token = create_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    session.add(
        AuthSessionORM(
            user_id=user_id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
        )
    )
    return token, expires_at


class FederatedContribution(BaseModel):
    """Strict schema for one anonymized, sanitized shared learning."""

    model_config = ConfigDict(extra="forbid")

    learning_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=10000)
    confidence: float = Field(ge=0.0, le=1.0)
    namespace: str = Field(default="global", pattern="^global$")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FederatedPushRequest(BaseModel):
    """Batch request intentionally has no user/device identifier field."""

    model_config = ConfigDict(extra="forbid")

    learnings: List[FederatedContribution] = Field(default_factory=list, max_length=100)


def _learning_payload(row: SharedLearningORM) -> Dict[str, Any]:
    metadata = row.learning_metadata or {}
    return {
        "learning_id": row.learning_id,
        "title": metadata.get("title", "Shared learning"),
        "content": row.content,
        "confidence": row.confidence,
        "namespace": row.namespace,
        "metadata": {
            key: metadata[key]
            for key in ("category", "tags", "sanitized")
            if key in metadata
        },
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _persist_contributions(
    contributions: List[FederatedContribution],
) -> tuple[List[Dict[str, Any]], int, int]:
    """Validate threshold, scrub again server-side, and deduplicate durably."""
    db = get_db_manager()
    session = db.get_session()
    accepted: List[Dict[str, Any]] = []
    rejected = 0
    try:
        threshold = get_settings().confidence_threshold
        for contribution in contributions:
            if contribution.confidence < threshold:
                rejected += 1
                continue

            safe = sanitizer.sanitize_learning(
                contribution.content,
                metadata=contribution.metadata,
            )
            safe_title = sanitizer.sanitize_text(contribution.title).strip()[:500]
            safe_content = safe["content"].strip()
            if not safe_title or not safe_content:
                rejected += 1
                continue

            metadata = dict(safe["metadata"])
            metadata["title"] = safe_title
            row = session.execute(
                select(SharedLearningORM).where(
                    SharedLearningORM.learning_id == contribution.learning_id
                )
            ).scalar_one_or_none()
            if row is None:
                row = SharedLearningORM(
                    learning_id=contribution.learning_id,
                    namespace="global",
                    content=safe_content,
                    confidence=contribution.confidence,
                    source_user_hash=None,
                    learning_metadata=metadata,
                )
                session.add(row)
                session.flush()
                accepted.append(_learning_payload(row))

        session.commit()
        return accepted, rejected, len(contributions) - len(accepted) - rejected
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _format_private_learning(content: Any) -> str:
    """Format an Agno user-memory/profile payload without rendering owner IDs."""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return content.strip()
    if isinstance(content, list):
        return "\n".join(
            text for item in content if (text := _format_private_learning(item))
        )
    if isinstance(content, dict):
        memories = content.get("memories")
        if isinstance(memories, list):
            return "\n".join(
                text for item in memories if (text := _format_private_learning(item))
            )
        private_fields = {
            "user_id", "agent_id", "team_id", "created_at", "updated_at",
            "id", "namespace",
        }
        lines = []
        for key, value in content.items():
            if key in private_fields or value is None or value == "":
                continue
            if isinstance(value, (dict, list)):
                rendered = _format_private_learning(value)
            else:
                rendered = str(value)
            if rendered:
                lines.append(f"{key.replace('_', ' ').title()}: {rendered}")
        return "\n".join(lines)
    if content is None:
        return ""
    return str(content)


@app.on_event("startup")
async def initialize_database() -> None:
    """Ensure app-owned tables, including the durable federated store, exist."""
    get_db_manager().create_tables()
    global federation_listener_task
    if settings.federated_listener_enabled:
        federation_listener_task = asyncio.create_task(_federation_listener())


@app.post("/auth/register", status_code=201)
async def register_account(req: CredentialsRequest):
    """Create a local account without email verification."""
    username = req.username.strip()
    try:
        normalized = normalize_username(username)
        password_hash = hash_password(req.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session = get_db_manager().get_session()
    try:
        existing = session.execute(
            select(UserAccountORM).where(UserAccountORM.username_normalized == normalized)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="That username is already registered")

        user_id = str(uuid4())
        account = UserAccountORM(
            user_id=user_id,
            username=username,
            username_normalized=normalized,
            password_hash=password_hash,
        )
        session.add(account)
        session.add(UserProfileORM(user_id=user_id, name=username))
        session.flush()
        token, expires_at = _issue_session(session, user_id)
        session.commit()
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_at": expires_at.isoformat(),
            "user": {"user_id": user_id, "username": username},
        }
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        logger.exception("Local account registration failed")
        # Hide DB details but tell the caller if a concurrent username claim won.
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="That username is already registered") from exc
        raise HTTPException(status_code=503, detail="Could not create the local account") from exc
    finally:
        session.close()


@app.post("/auth/login")
async def login_account(req: CredentialsRequest):
    """Verify local credentials and issue a 30-day opaque bearer token."""
    try:
        normalized = normalize_username(req.username)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    session = get_db_manager().get_session()
    try:
        account = session.execute(
            select(UserAccountORM).where(UserAccountORM.username_normalized == normalized)
        ).scalar_one_or_none()
        if account is None or not verify_password(req.password, account.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token, expires_at = _issue_session(session, account.user_id)
        session.commit()
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_at": expires_at.isoformat(),
            "user": {"user_id": account.user_id, "username": account.username},
        }
    finally:
        session.close()


@app.get("/auth/me")
async def who_am_i(current: AuthenticatedUser = Depends(get_current_user)):
    return {"user_id": current.user_id, "username": current.username}


@app.post("/auth/logout")
async def logout(current: AuthenticatedUser = Depends(get_current_user)):
    session = get_db_manager().get_session()
    try:
        token_session = session.execute(
            select(AuthSessionORM).where(AuthSessionORM.token_hash == current.token_hash)
        ).scalar_one_or_none()
        if token_session is not None:
            token_session.revoked_at = datetime.now(timezone.utc)
            session.commit()
        return {"status": "ok"}
    finally:
        session.close()


async def _federation_listener() -> None:
    """Keep a WebSocket subscription open for near-real-time global updates."""
    from agno.learn.stores import LearnedKnowledgeStore

    from fedMeta.federated.coordinator import FederatedLearningCoordinator
    from fedMeta.federated.realtime_sync import RealtimeSyncClient
    from fedMeta.learning.shared_knowledge import SharedKnowledgeManager

    client = RealtimeSyncClient()
    manager = SharedKnowledgeManager(namespace="global")
    learned_config = manager.get_learned_knowledge_config()
    learned_config.knowledge = manager.get_knowledge()
    learned_config.agent_can_save = False
    store = LearnedKnowledgeStore(config=learned_config)
    coordinator = FederatedLearningCoordinator(
        user_id="federated-device",
        learned_knowledge_store=store,
        sync_client=client,
    )
    client.register_handler("new_learnings", coordinator.apply_broadcast)

    while True:
        try:
            if await client.connect():
                # Catch up any server updates missed while this app was offline.
                await coordinator.pull_and_apply()
                while client.is_connected:
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            await client.disconnect()
            raise
        except Exception:
            logger.exception("Federated WebSocket listener failed")
            await client.disconnect()
        await asyncio.sleep(5)


@app.on_event("shutdown")
async def stop_federation_listener() -> None:
    """Stop the background federation listener cleanly."""
    if federation_listener_task is not None:
        federation_listener_task.cancel()
        try:
            await federation_listener_task
        except asyncio.CancelledError:
            pass


# --- Profile Endpoints ---

@app.get("/profile/{user_id}")
async def get_profile(user_id: str, _current: AuthenticatedUser = Depends(require_path_user)):
    """Get user profile."""
    db = get_db_manager()
    session = db.get_session()
    try:
        from fedMeta.database import UserProfileORM
        orm = session.query(UserProfileORM).filter_by(user_id=user_id).first()
        if not orm:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {
            "user_id": orm.user_id,
            "name": orm.name,
            "role": orm.role,
            "expertise_level": orm.expertise_level,
            "communication_style": orm.communication_style,
            "preferred_format": orm.preferred_format,
            "domains": orm.domains or [],
            "custom_rules": orm.custom_rules or {},
        }
    finally:
        session.close()


@app.post("/profile/{user_id}")
async def save_profile(
    user_id: str,
    req: ProfileUpdateRequest,
    _current: AuthenticatedUser = Depends(require_path_user),
):
    """Create or update user profile."""
    db = get_db_manager()
    session = db.get_session()
    try:
        from fedMeta.database import UserProfileORM
        orm = session.query(UserProfileORM).filter_by(user_id=user_id).first()
        
        if orm:
            # Update existing
            for key, value in req.model_dump(exclude_none=True).items():
                setattr(orm, key, value)
        else:
            # Create new
            orm = UserProfileORM(
                user_id=user_id,
                name=req.name or "User",
                role=req.role,
                expertise_level=req.expertise_level,
                communication_style=req.communication_style,
                preferred_format=req.preferred_format,
                domains=req.domains or [],
                custom_rules=req.custom_rules or {},
            )
            session.add(orm)
        
        session.commit()
        return {"status": "ok", "user_id": user_id}
    finally:
        session.close()


# --- Tools Endpoints ---

@app.get("/tools/{user_id}")
async def list_tools(user_id: str, _current: AuthenticatedUser = Depends(require_path_user)):
    """List all registered tools."""
    db = get_db_manager()
    session = db.get_session()
    try:
        from fedMeta.database import APIToolRegistryORM
        tools = session.query(APIToolRegistryORM).filter_by(owner_user_id=user_id).all()
        return [
            {
                "endpoint_id": t.id,
                "name": t.name,
                "description": t.description,
                "method": t.method,
                "url": t.url,
                "headers": t.headers or {},
                "input_schema": t.input_schema or {},
                "output_schema": t.output_schema or {},
                "is_active": t.is_active,
                "tags": t.tags or [],
            }
            for t in tools
        ]
    finally:
        session.close()


@app.post("/tools/{user_id}")
async def register_tool(
    user_id: str,
    req: ToolRegisterRequest,
    _current: AuthenticatedUser = Depends(require_path_user),
):
    """Register a new API endpoint tool."""
    db = get_db_manager()
    session = db.get_session()
    try:
        from fedMeta.database import APIToolRegistryORM
        secret_header_names = {"authorization", "x-api-key", "api-key", "x-auth-token"}
        for header_name, header_value in req.headers.items():
            if header_name.casefold() in secret_header_names and not re.search(
                r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", header_value
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Header {header_name!r} appears to contain a secret. "
                        "Use an environment placeholder such as ${WEB_SEARCH_API_TOKEN}."
                    ),
                )
        existing = session.query(APIToolRegistryORM).filter_by(
            name=req.name, owner_user_id=user_id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Tool '{req.name}' already exists")
        
        tool = APIToolRegistryORM(
            name=req.name,
            owner_user_id=user_id,
            url=req.url,
            method=req.method.upper(),
            description=req.description,
            headers=req.headers,
            input_schema=req.input_schema,
            output_schema=req.output_schema,
            tags=req.tags,
        )
        session.add(tool)
        session.commit()
        return {"status": "ok", "name": req.name}
    finally:
        session.close()


@app.patch("/tools/{user_id}/{tool_name}")
async def update_tool(
    user_id: str,
    tool_name: str,
    req: ToolUpdateRequest,
    _current: AuthenticatedUser = Depends(require_path_user),
):
    """Update a tool's status."""
    db = get_db_manager()
    session = db.get_session()
    try:
        from fedMeta.database import APIToolRegistryORM
        tool = session.query(APIToolRegistryORM).filter_by(
            name=tool_name, owner_user_id=user_id
        ).first()
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")
        
        if req.is_active is not None:
            tool.is_active = req.is_active
        if req.description is not None:
            tool.description = req.description
        if req.tags is not None:
            tool.tags = req.tags
        
        session.commit()
        return {"status": "ok"}
    finally:
        session.close()


@app.delete("/tools/{user_id}/{tool_name}")
async def delete_tool(
    user_id: str,
    tool_name: str,
    _current: AuthenticatedUser = Depends(require_path_user),
):
    """Delete a tool."""
    db = get_db_manager()
    session = db.get_session()
    try:
        from fedMeta.database import APIToolRegistryORM
        tool = session.query(APIToolRegistryORM).filter_by(
            name=tool_name, owner_user_id=user_id
        ).first()
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")
        session.delete(tool)
        session.commit()
        return {"status": "ok"}
    finally:
        session.close()


# --- Learning Endpoints ---

@app.get("/learning/{user_id}")
async def get_learnings(user_id: str, _current: AuthenticatedUser = Depends(require_path_user)):
    """Return local Agno learnings plus centrally federated learnings."""
    db = get_db_manager()
    session = db.get_session()
    try:
        from fedMeta.database import SharedLearningORM
        federated = session.query(SharedLearningORM).filter_by(namespace="global").all()
        federated_items = [
            {
                "learning_id": l.learning_id,
                "title": (l.learning_metadata or {}).get("title", "Shared learning"),
                "content": l.content,
                "category": (l.learning_metadata or {}).get("category", "general"),
                "confidence": l.confidence,
                "namespace": l.namespace,
                "scope": "federated",
                "created_at": l.created_at.isoformat(),
            }
            for l in federated
        ]
    finally:
        session.close()

    # Agno LearnedKnowledge lives in the local PgVector store. Keep this
    # separate from server contributions so the user can see local-only rules.
    local_items: List[Dict[str, Any]] = []
    try:
        from fedMeta.learning.shared_knowledge import SharedKnowledgeManager

        for row in SharedKnowledgeManager(namespace="user").get_all_learnings(
            limit=200,
            namespace="user",
            user_id=user_id,
        ):
            metadata = row.get("meta_data") or {}
            if metadata.get("namespace") != "user" or metadata.get("user_id") != user_id:
                continue
            raw_content = row.get("content") or ""
            try:
                learned = json.loads(raw_content) if isinstance(raw_content, str) else {}
            except (TypeError, json.JSONDecodeError):
                learned = {}
            if not isinstance(learned, dict):
                learned = {}
            content = learned.get("learning") or raw_content
            if not isinstance(content, str) or not content.strip():
                continue
            created_at = row.get("created_at")
            try:
                confidence = float(metadata.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            local_items.append({
                "learning_id": f"local:{row.get('id')}",
                "title": str(learned.get("title") or row.get("name") or "Local learning"),
                "content": content,
                "category": "local",
                "confidence": confidence,
                "namespace": "user",
                "scope": "local",
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or ""),
            })
    except Exception:
        # PostgreSQL/PgVector may be unavailable while the UI still needs to
        # display durable centrally federated learnings.
        logger.exception("Could not read local Agno learnings for the dashboard")

    # Agno's user_memory and user_profile stores are persisted in its own
    # PostgresDb learnings table, not in the PgVector knowledge table above.
    # Include those records too; otherwise AGENTIC memory/profile updates work
    # in chat but appear missing from this dashboard.
    try:
        from agno.db.postgres import PostgresDb

        agno_db = PostgresDb(
            db_url=get_settings().database_url,
            learnings_table="agno_learnings_store",
            db_schema="ai",
        )
        for learning_type, title in (
            ("user_memory", "User memory"),
            ("user_profile", "Learned user profile"),
        ):
            records = agno_db.get_learnings(
                learning_type=learning_type,
                user_id=user_id,
                limit=100,
            )
            for record in records:
                structured_content = record.get("content")
                memory_items = (
                    structured_content.get("memories")
                    if learning_type == "user_memory" and isinstance(structured_content, dict)
                    else None
                )
                if isinstance(memory_items, list) and memory_items:
                    for memory_index, memory in enumerate(memory_items):
                        content = _format_private_learning(memory)
                        if not content.strip():
                            continue
                        local_items.append({
                            "learning_id": f"agno:{record.get('id')}:{memory_index}",
                            "title": (
                                str(memory.get("topic") or memory.get("title") or title)
                                if isinstance(memory, dict)
                                else title
                            ),
                            "content": content,
                            "category": learning_type,
                            "confidence": 0.0,
                            "namespace": "user",
                            "scope": "local",
                            "created_at": str(record.get("updated_at") or record.get("created_at") or ""),
                        })
                    continue

                content = _format_private_learning(structured_content)
                if not content.strip():
                    continue
                record_id = str(record.get("id") or f"{learning_type}-{len(local_items)}")
                created_at = record.get("updated_at") or record.get("created_at")
                if isinstance(created_at, datetime):
                    created_at = created_at.isoformat()
                elif isinstance(created_at, (int, float)):
                    created_at = datetime.fromtimestamp(created_at, timezone.utc).isoformat()
                local_items.append({
                    "learning_id": f"agno:{record_id}",
                    "title": title,
                    "content": content,
                    "category": learning_type,
                    "confidence": 0.0,
                    "namespace": "user",
                    "scope": "local",
                    "created_at": str(created_at or ""),
                })
    except Exception:
        logger.exception("Could not read Agno user memory/profile for the dashboard")

    combined = local_items + federated_items
    combined.sort(key=lambda item: item["created_at"], reverse=True)
    return combined


# --- Federated Sync Endpoints ---

@app.get("/federated/status/{user_id}")
async def get_sync_status(user_id: str, _current: AuthenticatedUser = Depends(require_path_user)):
    """Get federated sync status."""
    db = get_db_manager()
    session = db.get_session()
    try:
        from fedMeta.database import FederatedOutboxORM, FederatedSyncStateORM
        state = session.query(FederatedSyncStateORM).filter_by(user_id=user_id).first()
        last_push = (
            session.query(FederatedOutboxORM.sent_at)
            .filter(
                FederatedOutboxORM.user_id == user_id,
                FederatedOutboxORM.sent_at.is_not(None),
            )
            .order_by(FederatedOutboxORM.sent_at.desc())
            .first()
        )
        pending_count = (
            session.query(FederatedOutboxORM)
            .filter(
                FederatedOutboxORM.user_id == user_id,
                FederatedOutboxORM.sent_at.is_(None),
            )
            .count()
        )
        if not state:
            return {
                "last_push": last_push[0].isoformat() if last_push and last_push[0] else None,
                "last_pull": None,
                "total_pushed": 0,
                "total_pulled": 0,
                "pending_count": pending_count,
            }
        return {
            "last_push": last_push[0].isoformat() if last_push and last_push[0] else None,
            "last_pull": state.last_sync_at.isoformat() if state.last_sync_at else None,
            "total_pushed": state.last_pushed_count,
            "total_pulled": state.last_pulled_count,
            "pending_count": pending_count,
        }
    finally:
        session.close()


@app.post("/federated/sync/{user_id}")
async def trigger_sync(user_id: str, _current: AuthenticatedUser = Depends(require_path_user)):
    """Retry the local outbox and apply newly received global rules."""
    try:
        from fedMeta.agent_builder import build_meta_agent
        from fedMeta.federated.coordinator import FederatedLearningCoordinator

        agent = build_meta_agent(user_id=user_id)
        store = getattr(agent, "fedmeta_learned_knowledge_store", None)
        if store is None:
            raise HTTPException(status_code=503, detail="Agno learned-knowledge store is unavailable")
        outcome = await FederatedLearningCoordinator(user_id, store).sync()
        return {"status": "ok", **outcome}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Federated sync failed")
        raise HTTPException(status_code=503, detail="Federated sync is temporarily unavailable") from exc


# --- Agent Chat ---

@app.post("/agent/chat", response_model=ChatResponse)
async def agent_chat(
    req: ChatRequest,
    current: AuthenticatedUser = Depends(get_current_user),
):
    """Chat with the FedMeta agent."""
    if not hmac.compare_digest(req.user_id, current.user_id):
        raise HTTPException(status_code=403, detail="Chat user does not match signed-in account")
    try:
        from fedMeta.agent_builder import build_meta_agent
        from fedMeta.learning.behavior_adapter import BehaviorAdapter
        from fedMeta.profile.manager import ProfileManager
        
        # Create profile manager and behavior adapter
        profile_manager = ProfileManager()
        behavior_adapter = BehaviorAdapter(profile_manager=profile_manager)
        
        # Build agent with profile adaptation
        agent = build_meta_agent(
            user_id=req.user_id,
            behavior_adapter=behavior_adapter,
        )
        
        # Get response
        run_output = await asyncio.to_thread(agent.run, req.message)
        
        # Extract only the generated assistant text
        final_content = run_output.content if run_output and run_output.content else ""

        # Federation is a separate post-run step. Only the guarded save_learning
        # tool can populate this list, and only explicitly consented,
        # threshold-passing items are queued. The durable outbox retries errors.
        learned_store = getattr(agent, "fedmeta_learned_knowledge_store", None)
        sync_result: Dict[str, int] = {}
        if learned_store is not None:
            from fedMeta.federated.coordinator import FederatedLearningCoordinator

            candidates = list(
                getattr(learned_store, "fedmeta_pending_candidates", [])
            )
            learned_store.fedmeta_pending_candidates = []
            sync_result = await FederatedLearningCoordinator(
                req.user_id, learned_store
            ).sync(candidates)
            logger.info("Federated post-run sync: %s", sync_result)
        
        return ChatResponse(
            response=str(final_content),
            user_id=req.user_id,
        )
    except Exception as e:
        logger.error("Agent chat error: %s", str(e))
        raise HTTPException(
            status_code=502,
            detail="The agent could not complete this request. Check the backend logs and model configuration.",
        ) from e


@app.post("/agent/chat/stream")
async def agent_chat_stream(
    req: ChatRequest,
    current: AuthenticatedUser = Depends(get_current_user),
):
    """Stream Agno text deltas to the desktop client using Server-Sent Events."""
    if not hmac.compare_digest(req.user_id, current.user_id):
        raise HTTPException(status_code=403, detail="Chat user does not match signed-in account")
    try:
        from fedMeta.agent_builder import build_meta_agent
        from fedMeta.learning.behavior_adapter import BehaviorAdapter
        from fedMeta.profile.manager import ProfileManager

        manager = ProfileManager()
        adapter = BehaviorAdapter(profile_manager=manager)
        agent = build_meta_agent(user_id=req.user_id, behavior_adapter=adapter)
        run_events = agent.arun(req.message, stream=True, stream_events=True)
    except Exception as exc:
        logger.exception("Could not start streaming agent run")
        raise HTTPException(
            status_code=502,
            detail="The agent could not start this request. Check the backend logs and model configuration.",
        ) from exc

    async def generate_events():
        from agno.run.agent import RunCompletedEvent, RunContentEvent, RunErrorEvent

        chunks: List[str] = []
        try:
            yield "event: status\ndata: {\"status\": \"thinking\"}\n\n"
            async for event in run_events:
                if isinstance(event, RunContentEvent):
                    text = event.content
                    if isinstance(text, str) and text:
                        chunks.append(text)
                        yield f"event: token\ndata: {json.dumps({'content': text}, ensure_ascii=False)}\n\n"
                elif isinstance(event, RunErrorEvent):
                    logger.error("Agno streaming run failed (%s)", event.error_type or "run error")
                    yield "event: error\ndata: {\"detail\": \"The agent run failed. Please try again.\"}\n\n"
                    return
                elif isinstance(event, RunCompletedEvent):
                    # Some providers emit only a completed response rather than
                    # text deltas. Keep this endpoint usable for those models.
                    if not chunks and isinstance(event.content, str) and event.content:
                        chunks.append(event.content)
                        yield f"event: token\ndata: {json.dumps({'content': event.content}, ensure_ascii=False)}\n\n"

            # A run may finish with an empty response; report completion either way.
            learned_store = getattr(agent, "fedmeta_learned_knowledge_store", None)
            if learned_store is not None:
                from fedMeta.federated.coordinator import FederatedLearningCoordinator

                candidates = list(getattr(learned_store, "fedmeta_pending_candidates", []))
                learned_store.fedmeta_pending_candidates = []
                result = await FederatedLearningCoordinator(req.user_id, learned_store).sync(candidates)
                logger.info("Federated streaming post-run sync: %s", result)

            yield f"event: done\ndata: {json.dumps({'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
        except Exception:
            logger.exception("Streaming agent request failed")
            yield "event: error\ndata: {\"detail\": \"The agent run failed. Please try again.\"}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/agent/history/{user_id}")
async def get_agent_history(
    user_id: str,
    last_n_runs: int = Query(default=50, ge=1, le=100),
    _current: AuthenticatedUser = Depends(require_path_user),
):
    """Return persisted user/assistant text from this user's Agno session only."""
    try:
        from fedMeta.agent_builder import build_meta_agent

        agent = build_meta_agent(user_id=user_id)
        agno_messages = agent.get_chat_history(last_n_runs=last_n_runs)
        history: List[Dict[str, Any]] = []
        for index, message in enumerate(agno_messages):
            role = getattr(message, "role", None)
            content = getattr(message, "content", None)
            # Exclude tool/system messages, tool-call-only assistant entries,
            # and non-text multimodal payloads from the simple chat UI.
            if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
                continue

            created_at = getattr(message, "created_at", None)
            if isinstance(created_at, (int, float)):
                timestamp = datetime.fromtimestamp(created_at, tz=timezone.utc)
            elif isinstance(created_at, datetime):
                timestamp = created_at
            else:
                timestamp = datetime.now(timezone.utc)

            history.append({
                "id": str(getattr(message, "id", None) or f"{role}-{created_at}-{index}"),
                "role": role,
                "content": content,
                "timestamp": timestamp.isoformat(),
            })

        history.sort(key=lambda item: item["timestamp"])
        return {"user_id": user_id, "messages": history}
    except Exception as exc:
        logger.exception("Could not load Agno chat history")
        raise HTTPException(status_code=503, detail="Chat history is temporarily unavailable") from exc


# --- Federated Push/Pull (for other clients) ---

@app.post("/federated/push")
async def push_learnings(request: FederatedPushRequest):
    """Accept anonymous, confidence-qualified learnings durably."""
    try:
        accepted, rejected, duplicates = _persist_contributions(request.learnings)
    except Exception as exc:
        logger.exception("Could not persist federated contributions")
        raise HTTPException(status_code=503, detail="Federated store unavailable") from exc

    if accepted:
        await _broadcast({"type": "new_learnings", "payload": {"learnings": accepted}})
    return {
        "status": "ok",
        "pushed": len(accepted),
        "duplicates": duplicates,
        "rejected": rejected,
    }


@app.get("/federated/pull")
async def pull_learnings(
    namespace: str = Query(default="global"),
    limit: int = Query(default=10, ge=1, le=100),
    since: Optional[datetime] = Query(default=None),
    offset: int = Query(default=0, ge=0),
):
    """Return durable global learnings, optionally newer than a cursor."""
    db = get_db_manager()
    session = db.get_session()
    try:
        stmt = select(SharedLearningORM).where(
            SharedLearningORM.namespace == namespace,
            SharedLearningORM.confidence >= get_settings().confidence_threshold,
        )
        if since is not None:
            stmt = stmt.where(SharedLearningORM.created_at > since)
        stmt = (
            stmt.order_by(SharedLearningORM.created_at.asc(), SharedLearningORM.learning_id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = session.execute(stmt).scalars().all()
        return {
            "status": "ok",
            "learnings": [_learning_payload(row) for row in rows],
            "total": len(rows),
        }
    finally:
        session.close()


@app.post("/knowledge/query")
async def query_knowledge(request: Dict[str, Any]):
    """Search durable global learnings by keyword (vector retrieval is local Agno)."""
    query = request.get("query", "").lower()
    limit = min(max(int(request.get("limit", 5)), 1), 50)
    db = get_db_manager()
    session = db.get_session()
    try:
        rows = session.execute(
            select(SharedLearningORM)
            .where(
                SharedLearningORM.namespace == request.get("namespace", "global"),
                SharedLearningORM.content.ilike(f"%{query}%"),
            )
            .order_by(SharedLearningORM.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return {"status": "ok", "results": [_learning_payload(row) for row in rows], "total": len(rows)}
    finally:
        session.close()


# --- WebSocket ---

@app.websocket("/federated/stream")
async def federated_stream(websocket: WebSocket):
    """WebSocket for real-time federated sync."""
    await websocket.accept()
    connected_websockets.add(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
                msg_type = message.get("type", "unknown")
                payload = message.get("payload", {})
                
                if msg_type == "push":
                    contributions = [
                        FederatedContribution.model_validate(item)
                        for item in payload.get("learnings", [])
                    ]
                    accepted, rejected, duplicates = _persist_contributions(contributions)
                    if accepted:
                        await _broadcast({"type": "new_learnings", "payload": {"learnings": accepted}})
                    await websocket.send_json({
                        "type": "push_ack",
                        "payload": {"pushed": len(accepted), "rejected": rejected, "duplicates": duplicates},
                    })
                
                elif msg_type == "pull":
                    db = get_db_manager()
                    session = db.get_session()
                    try:
                        rows = session.execute(
                            select(SharedLearningORM)
                            .where(
                                SharedLearningORM.namespace == payload.get("namespace", "global"),
                                SharedLearningORM.confidence >= get_settings().confidence_threshold,
                            )
                            .order_by(SharedLearningORM.created_at.desc())
                            .limit(min(max(int(payload.get("limit", 10)), 1), 100))
                        ).scalars().all()
                        learnings = [_learning_payload(row) for row in rows]
                    finally:
                        session.close()
                    await websocket.send_json({"type": "pull_response", "payload": {"learnings": learnings}})
                
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong", "payload": {}})
            except json.JSONDecodeError:
                pass
            except (ValueError, TypeError, KeyError):
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": "Invalid federated message payload"},
                })
    except WebSocketDisconnect:
        pass
    finally:
        connected_websockets.discard(websocket)


# --- Health ---

@app.get("/health")
async def health_check():
    """Health check."""
    return {"status": "ok", "version": "0.1.0", "timestamp": datetime.now(timezone.utc)}


# --- Main ---

def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
