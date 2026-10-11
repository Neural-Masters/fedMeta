"""PII sanitization for federated learnings.

Removes personally identifiable information from learnings before
they are shared with the central server, ensuring privacy preservation
in the federated learning pipeline.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LearningSanitizer:
    """Sanitizes learnings by removing PII before federated sharing.

    Uses regex-based detection and removal of common PII patterns
    including emails, phone numbers, SSNs, credit cards, IP addresses,
    and person names (heuristic-based).
    """

    # Regex patterns for common PII
    PATTERNS = {
        "email": re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        ),
        "phone": re.compile(
            r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
        ),
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "credit_card": re.compile(
            r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
        ),
        "ip_address": re.compile(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        ),
        "url_with_credentials": re.compile(
            r"(https?://)[^/\s]+:[^@\s]+@"
        ),
        "date_of_birth": re.compile(
            r"\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b"
        ),
        "api_key": re.compile(
            r"\b(?:api[_-]?key|apikey|token|secret)[\s]*[=:][\s]*[\"']?[A-Za-z0-9_\-]{16,}[\"']?",
            re.IGNORECASE,
        ),
        "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE),
    }

    # Common first names for heuristic PII detection (top 100)
    COMMON_NAMES = {
        "james", "john", "robert", "michael", "william", "david",
        "richard", "joseph", "thomas", "charles", "mary", "patricia",
        "jennifer", "linda", "elizabeth", "barbara", "susan", "jessica",
        "sarah", "karen", "nancy", "lisa", "betty", "margaret", "sandra",
        "ashley", "kimberly", "emily", "donna", "michelle", "dorothy",
        "carol", "amanda", "melissa", "deborah", "stephanie", "rebecca",
        "laura", "sharon", "cynthia", "kathleen", "amy", "shirley",
        "angela", "helen", "anna", "brenda", "pamela", "nicole",
        "emma", "samantha", "katherine", "christine", "debra", "rachel",
        "catherine", "carolyn", "janet", "virginia", "maria", "olivia",
        "heather", "diane", "julie", "joyce", "victoria", "kelly",
        "christina", "lauren", "joan", "evelyn", "judith", "megan",
        "cheryl", "andrea", "hannah", "jacqueline", "martha", "gloria",
        "teresa", "ann", "sara", "madison", "frances", "kathryn",
        "janice", "jean", "abigail", "alice", "judy", "sophia",
        "grace", "denise", "amber", "doris", "marilyn", "danielle",
        "beverly", "isabella", "theresa", "diana", "natalie", "brittany",
        "charlotte", "marie", "kayla", "alexis", "lori",
    }

    def __init__(self, custom_patterns: Optional[Dict[str, str]] = None) -> None:
        """Initialize sanitizer with optional custom patterns.

        Args:
            custom_patterns: Additional regex patterns as {name: pattern}.
        """
        self.patterns = dict(self.PATTERNS)
        if custom_patterns:
            for name, pattern in custom_patterns.items():
                self.patterns[name] = re.compile(pattern)

    def sanitize_text(self, text: str) -> str:
        """Remove PII from a text string.

        Args:
            text: The text to sanitize.

        Returns:
            Sanitized text with PII replaced by placeholders.
        """
        sanitized = text
        replacements = {
            "email": "[EMAIL]",
            "phone": "[PHONE]",
            "ssn": "[SSN]",
            "credit_card": "[CREDIT_CARD]",
            "ip_address": "[IP]",
            "url_with_credentials": r"\1[CREDENTIALS_REMOVED]@",
            "date_of_birth": "[DOB]",
            "api_key": "[API_KEY]",
            "bearer_token": "Bearer [TOKEN]",
        }

        for pii_type, pattern in self.patterns.items():
            replacement = replacements.get(pii_type, f"[{pii_type.upper()}]")
            sanitized = pattern.sub(replacement, sanitized)

        return sanitized

    def sanitize_learning(
        self,
        content: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sanitize a complete learning entry.

        Args:
            content: The learning content.
            user_id: Original user_id (will be hashed).
            metadata: Associated metadata.

        Returns:
            Dictionary with sanitized content, hashed user_id, and
            sanitized metadata.
        """
        sanitized_content = self.sanitize_text(content)

        # Use an allowlist: metadata must never accidentally carry user IDs,
        # raw conversation fragments, headers, or arbitrary tool output.
        metadata = metadata or {}
        sanitized_metadata: Dict[str, Any] = {"sanitized": True}
        category = metadata.get("category")
        if isinstance(category, str):
            sanitized_metadata["category"] = self.sanitize_text(category)[:80]
        tags = metadata.get("tags")
        if isinstance(tags, list):
            sanitized_metadata["tags"] = [
                self.sanitize_text(tag)[:80]
                for tag in tags
                if isinstance(tag, str)
            ][:20]

        return {
            "content": sanitized_content,
            "metadata": sanitized_metadata,
        }

    def sanitize_learnings(
        self,
        learnings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Sanitize a batch of learnings.

        Args:
            learnings: List of learning dictionaries with 'content',
                optional 'user_id', and optional 'metadata'.

        Returns:
            List of sanitized learning dictionaries.
        """
        sanitized = []
        for learning in learnings:
            content = learning.get("content") or learning.get("learning") or ""
            result = self.sanitize_learning(content=content, metadata=learning.get("metadata"))
            title = learning.get("title")
            if isinstance(title, str):
                result["title"] = self.sanitize_text(title)[:500]
            learning_id = learning.get("learning_id")
            if isinstance(learning_id, str):
                result["learning_id"] = learning_id
            try:
                confidence = float(learning.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            result["confidence"] = min(max(confidence, 0.0), 1.0)
            result["namespace"] = "global"
            sanitized.append(result)

        logger.info("Sanitized %d learnings", len(sanitized))
        return sanitized

    def contains_pii(self, text: str) -> bool:
        """Check if text contains potential PII.

        Args:
            text: The text to check.

        Returns:
            True if PII patterns are detected.
        """
        for pattern in self.patterns.values():
            if pattern.search(text):
                return True
        return False

    def anonymize_user_id(self, user_id: str) -> str:
        """Create an anonymized hash of a user_id.

        Args:
            user_id: The original user identifier.

        Returns:
            A deterministic hash string.
        """
        return hashlib.sha256(user_id.encode()).hexdigest()[:16]
