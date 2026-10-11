"""Real-time federated sync client.

WebSocket-based client for pushing sanitized learnings to and
pulling global learnings from the central server.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

import httpx

from fedMeta.config import get_settings
from fedMeta.federated.sanitizer import LearningSanitizer

logger = logging.getLogger(__name__)


class RealtimeSyncClient:
    """Client for real-time federated learning synchronization.

    Provides methods to push sanitized learnings to the server and
    pull global rules.  Uses WebSocket for real-time bidirectional
    sync and HTTP for initial batch operations.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        sanitizer: Optional[LearningSanitizer] = None,
    ) -> None:
        self.settings = get_settings()
        self.server_url = server_url or self.settings.server_url
        self.ws_url = ws_url or self.settings.server_ws_url
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self.settings.confidence_threshold
        )
        self.sanitizer = sanitizer or LearningSanitizer()
        self._ws = None
        self._connected = False
        self._listener_task: Optional[asyncio.Task] = None
        self._message_handlers: Dict[str, Callable] = {}

    async def connect(self) -> bool:
        """Establish WebSocket connection to the server.

        Returns:
            True if connection successful.
        """
        if self._connected:
            return True
        try:
            import websockets

            ws_endpoint = f"{self.ws_url}/federated/stream"
            self._ws = await websockets.connect(ws_endpoint)
            self._connected = True
            logger.info("Connected to federated sync server at %s", ws_endpoint)

            # Start message listener
            self._listener_task = asyncio.create_task(self._listen())
            return True

        except ImportError:
            logger.warning("websockets library not available, sync disabled")
            return False
        except Exception as e:
            logger.error("Failed to connect to sync server: %s", str(e))
            return False

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._connected = False
            if self._listener_task and not self._listener_task.done():
                self._listener_task.cancel()
            self._listener_task = None
            logger.info("Disconnected from federated sync server")

    async def push_learnings(
        self,
        learnings: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Push sanitized learnings to the central server.

        Learnings are sanitized and filtered by confidence threshold
        before being sent.

        Args:
            learnings: List of learning dictionaries.

        Returns:
            Server response.
        """
        # Fail closed: only explicitly scored, high-confidence insights sync.
        filtered = [
            l for l in learnings
            if isinstance(l.get("confidence"), (int, float))
            and self.confidence_threshold <= float(l["confidence"]) <= 1.0
            and (l.get("content") or l.get("learning"))
        ]

        if not filtered:
            logger.debug("No learnings above confidence threshold to push")
            return {"status": "ok", "pushed": 0}

        # Sanitize
        sanitized = self.sanitizer.sanitize_learnings(filtered)

        # Send via HTTP POST
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.server_url}/federated/push",
                    json={"learnings": sanitized},
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()
                logger.info("Pushed %d learnings to server", len(sanitized))
                return result

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error("Failed to push learnings: %s", str(e))
            return {"status": "error", "error": str(e)}

    async def pull_learnings(
        self,
        namespace: str = "global",
        limit: int = 10,
        since: Optional[str] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Pull global learnings from the server.

        Args:
            namespace: Knowledge namespace to pull from.
            limit: Maximum number of learnings.

        Returns:
            Server response with learnings.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.server_url}/federated/pull",
                    params={
                        "namespace": namespace,
                        "limit": limit,
                        "offset": offset,
                        **({"since": since} if since else {}),
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()
                logger.info(
                    "Pulled %d learnings from server", len(result.get("learnings", []))
                )
                return result

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error("Failed to pull learnings: %s", str(e))
            return {"status": "error", "error": str(e), "learnings": []}

    async def query_knowledge(
        self,
        query: str,
        namespace: str = "global",
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Query the global knowledge base.

        Args:
            query: Search query.
            namespace: Knowledge namespace.
            limit: Maximum results.

        Returns:
            Server response with matching knowledge.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.server_url}/knowledge/query",
                    json={
                        "query": query,
                        "namespace": namespace,
                        "limit": limit,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error("Failed to query knowledge: %s", str(e))
            return {"status": "error", "error": str(e), "results": []}

    async def send_realtime_update(self, message: Dict[str, Any]) -> None:
        """Send a real-time update via WebSocket.

        Args:
            message: The message payload to send.
        """
        if not self._connected or not self._ws:
            logger.warning("Not connected to sync server, cannot send update")
            return

        try:
            await self._ws.send(json.dumps(message))
        except Exception as e:
            logger.error("Failed to send realtime update: %s", str(e))

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for incoming WebSocket messages.

        Args:
            message_type: Type of message to handle.
            handler: Callback function.
        """
        self._message_handlers[message_type] = handler

    async def _listen(self) -> None:
        """Background task to listen for WebSocket messages."""
        if not self._ws:
            return

        try:
            async for raw_message in self._ws:
                try:
                    message = json.loads(raw_message)
                    msg_type = message.get("type", "unknown")
                    handler = self._message_handlers.get(msg_type)
                    if handler:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                except json.JSONDecodeError:
                    logger.warning("Received malformed message from server")
        except Exception as e:
            logger.error("WebSocket listener error: %s", str(e))
        finally:
            self._connected = False

    @property
    def is_connected(self) -> bool:
        """Return True if WebSocket is connected."""
        return self._connected
