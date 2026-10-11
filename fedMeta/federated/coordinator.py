"""Federated-learning orchestration for Agno LearnedKnowledge.

Only insights explicitly approved for global sharing are staged. Conversation
messages, profile fields and raw user IDs are never sent to the server.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from fedMeta.config import get_settings
from fedMeta.database import (
    FederatedOutboxORM,
    FederatedReceiptORM,
    FederatedSyncStateORM,
    get_db_manager,
)
from fedMeta.federated.realtime_sync import RealtimeSyncClient
from fedMeta.federated.sanitizer import LearningSanitizer

logger = logging.getLogger(__name__)


class FederatedLearningCoordinator:
    """Stage, push, pull and apply Agno learned knowledge safely."""

    def __init__(
        self,
        user_id: str,
        learned_knowledge_store: Any,
        sync_client: Optional[RealtimeSyncClient] = None,
    ) -> None:
        self.user_id = user_id  # Local partition key only; never sent remotely.
        self.store = learned_knowledge_store
        self.settings = get_settings()
        self.db = get_db_manager()
        self.sync_client = sync_client or RealtimeSyncClient(
            confidence_threshold=self.settings.confidence_threshold
        )
        self.sanitizer = LearningSanitizer()

    async def sync(self, candidates: Optional[List[Dict[str, Any]]] = None) -> Dict[str, int]:
        """Persist eligible candidates, push pending work, then apply globals."""
        self.db.create_tables()
        queued = self._queue_candidates(candidates or [])
        pushed = await self._push_pending()
        pulled, applied = await self._pull_and_apply()
        return {"queued": queued, "pushed": pushed, "pulled": pulled, "applied": applied}

    def _queue_candidates(self, candidates: List[Dict[str, Any]]) -> int:
        """Sanitize and durably queue only threshold-passing candidates."""
        session = self.db.get_session()
        queued = 0
        try:
            for candidate in candidates:
                try:
                    confidence = float(candidate.get("confidence", 0.0))
                except (TypeError, ValueError):
                    continue
                if not self.settings.confidence_threshold <= confidence <= 1.0:
                    continue

                title = self.sanitizer.sanitize_text(str(candidate.get("title", ""))).strip()
                content = self.sanitizer.sanitize_text(
                    str(candidate.get("learning") or candidate.get("content") or "")
                ).strip()
                tags = candidate.get("tags", [])
                safe_tags = [
                    self.sanitizer.sanitize_text(tag).strip()[:80]
                    for tag in tags[:20]
                    if isinstance(tag, str) and tag.strip()
                ] if isinstance(tags, list) else []

                if not title or not content:
                    continue
                # Stable ID makes HTTP retries idempotent without a device ID.
                fingerprint = f"{title.casefold()}\n{content.casefold()}"
                learning_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
                existing = session.execute(
                    select(FederatedOutboxORM).where(
                        FederatedOutboxORM.learning_id == learning_id
                    )
                ).scalar_one_or_none()
                if existing:
                    continue

                session.add(
                    FederatedOutboxORM(
                        user_id=self.user_id,
                        learning_id=learning_id,
                        title=title[:500],
                        content=content,
                        confidence=confidence,
                        learning_metadata={"category": "agent_learning", "tags": safe_tags},
                    )
                )
                queued += 1
            session.commit()
            return queued
        except Exception:
            session.rollback()
            logger.exception("Failed to queue federated learning candidates")
            return 0
        finally:
            session.close()

    async def _push_pending(self) -> int:
        session = self.db.get_session()
        try:
            rows = session.execute(
                select(FederatedOutboxORM)
                .where(
                    FederatedOutboxORM.user_id == self.user_id,
                    FederatedOutboxORM.sent_at.is_(None),
                )
                .order_by(FederatedOutboxORM.created_at)
                .limit(100)
            ).scalars().all()
            payload = [
                {
                    "learning_id": row.learning_id,
                    "title": row.title,
                    "content": row.content,
                    "confidence": row.confidence,
                    "namespace": "global",
                    "metadata": row.learning_metadata or {},
                }
                for row in rows
            ]
            if not payload:
                return 0

            response = await self.sync_client.push_learnings(payload)
            if response.get("status") != "ok":
                logger.warning("Federated push deferred; outbox remains pending")
                return 0

            sent_ids = {item["learning_id"] for item in payload}
            now = datetime.now(timezone.utc)
            for row in rows:
                if row.learning_id in sent_ids:
                    row.sent_at = now
            state = self._get_or_create_sync_state(session)
            state.last_pushed_count += int(response.get("pushed", 0))
            session.commit()
            return int(response.get("pushed", 0))
        except Exception:
            session.rollback()
            logger.exception("Federated push failed; queued items will retry later")
            return 0
        finally:
            session.close()

    async def _pull_and_apply(self) -> tuple[int, int]:
        session = self.db.get_session()
        try:
            state = self._get_or_create_sync_state(session)
            since = state.last_sync_at.isoformat() if state.last_sync_at else None
            try:
                offset = max(int(state.sync_token or 0), 0)
            except (TypeError, ValueError):
                offset = 0
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Could not read federated sync cursor")
            return 0, 0
        finally:
            session.close()

        pulled = 0
        applied = 0
        all_applied = True
        page_size = 100
        max_pages = 100  # Bound catch-up work to 10,000 entries per sync.
        completed = False

        for _ in range(max_pages):
            result = await self.sync_client.pull_learnings(
                namespace="global", limit=page_size, since=since, offset=offset
            )
            if result.get("status") != "ok":
                return pulled, applied
            entries = result.get("learnings", [])
            session = self.db.get_session()
            try:
                page_applied, page_failed = self._apply_entries(session, entries)
                state = self._get_or_create_sync_state(session)
                state.last_pulled_count += len(entries)
                state.sync_token = str(offset if page_failed else offset + len(entries))
                session.commit()
                pulled += len(entries)
                applied += page_applied
                all_applied = all_applied and page_failed == 0
            except Exception:
                session.rollback()
                logger.exception("Federated pull/apply page failed")
                return pulled, applied
            finally:
                session.close()

            if len(entries) < page_size:
                completed = True
                break
            offset += len(entries)

        # Advance the timestamp cursor only after all pages and entries were
        # applied. Otherwise failed items remain eligible for retry.
        if completed and all_applied:
            session = self.db.get_session()
            try:
                state = self._get_or_create_sync_state(session)
                state.last_sync_at = datetime.now(timezone.utc)
                state.sync_token = None
                session.commit()
            finally:
                session.close()
        elif not completed:
            logger.warning("Federated catch-up hit the per-sync page limit; will resume next sync")

        return pulled, applied

    async def pull_and_apply(self) -> tuple[int, int]:
        """Public pull operation used after WebSocket reconnection."""
        return await self._pull_and_apply()

    async def apply_broadcast(self, message: Dict[str, Any]) -> int:
        """Apply learnings from a real-time server broadcast idempotently."""
        payload = message.get("payload") or {}
        entries = payload.get("learnings", []) if isinstance(payload, dict) else []
        session = self.db.get_session()
        try:
            applied, _failed = self._apply_entries(session, entries)
            session.commit()
            return applied
        except Exception:
            session.rollback()
            logger.exception("Could not apply real-time federated update")
            return 0
        finally:
            session.close()

    def _apply_entries(self, session: Any, entries: List[Dict[str, Any]]) -> tuple[int, int]:
        """Validate and index incoming insights through Agno's learning store."""
        applied = 0
        failed = 0
        for item in entries:
            learning_id = item.get("learning_id")
            if not learning_id:
                failed += 1
                continue
            receipt = session.execute(
                select(FederatedReceiptORM).where(
                    FederatedReceiptORM.user_id == self.user_id,
                    FederatedReceiptORM.learning_id == learning_id,
                )
            ).scalar_one_or_none()
            if receipt:
                continue

            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue
            if not self.settings.confidence_threshold <= confidence <= 1.0:
                continue

            title = self.sanitizer.sanitize_text(str(item.get("title") or "Shared learning"))
            content = self.sanitizer.sanitize_text(str(item.get("content") or "")).strip()
            if not content:
                failed += 1
                continue
            raw_meta = item.get("metadata") or {}
            tags = raw_meta.get("tags", []) if isinstance(raw_meta, dict) else []
            safe_tags = [
                self.sanitizer.sanitize_text(tag)[:80]
                for tag in tags
                if isinstance(tag, str)
            ][:20]

            existing = self.store.search(query=content, namespace="global", limit=5)
            normalized_content = " ".join(content.casefold().split())
            already_saved = any(
                " ".join(str(getattr(entry, "learning", "")).casefold().split())
                == normalized_content
                for entry in existing
            )
            saved = already_saved or self.store.save(
                title=title[:500],
                learning=content,
                tags=list(dict.fromkeys([*safe_tags, "federated"])),
                namespace="global",
            )
            if not saved:
                failed += 1
                continue
            session.add(FederatedReceiptORM(user_id=self.user_id, learning_id=learning_id))
            applied += 1
        return applied, failed

    def _get_or_create_sync_state(self, session: Any) -> FederatedSyncStateORM:
        state = session.execute(
            select(FederatedSyncStateORM).where(
                FederatedSyncStateORM.user_id == self.user_id
            )
        ).scalar_one_or_none()
        if state is None:
            state = FederatedSyncStateORM(user_id=self.user_id)
            session.add(state)
            session.flush()
        return state
