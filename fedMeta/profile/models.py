"""UserProfile dataclass and related types."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class UserProfile:
    """Structured user profile for agent personalization.

    This profile captures the essential characteristics of a user that
    influence how the agent should interact with them.  It is used by
    the Learning Machine's User Profile store and injected into system
    prompts to guide agent behavior.

    Attributes:
        name: Display name of the user.
        role: Professional role (e.g., "software engineer", "data scientist").
        expertise_level: Skill level ("beginner", "intermediate", "advanced", "expert").
        communication_style: Preferred tone ("formal", "casual", "technical", "concise").
        preferred_format: Response format preference ("bullets", "paragraph", "code_first", "step_by_step").
        domains: List of domain interests (e.g., ["ml", "web_dev", "finance"]).
        custom_rules: Free-form custom rules and preferences.
    """

    name: str
    role: Optional[str] = None
    expertise_level: Optional[str] = None
    communication_style: Optional[str] = None
    preferred_format: Optional[str] = None
    domains: List[str] = field(default_factory=list)
    custom_rules: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UserProfile:
        """Create a UserProfile from a dictionary."""
        return cls(
            name=data.get("name", ""),
            role=data.get("role"),
            expertise_level=data.get("expertise_level"),
            communication_style=data.get("communication_style"),
            preferred_format=data.get("preferred_format"),
            domains=data.get("domains", []),
            custom_rules=data.get("custom_rules", {}),
        )

    def to_prompt_context(self) -> str:
        """Convert profile to a string suitable for system prompt injection.

        Returns a formatted string that can be embedded in the agent's
        system prompt to personalize responses.
        """
        parts: List[str] = [f"User name: {self.name}"]

        if self.role:
            parts.append(f"Role: {self.role}")
        if self.expertise_level:
            parts.append(f"Expertise level: {self.expertise_level}")
        if self.communication_style:
            parts.append(f"Preferred communication style: {self.communication_style}")
        if self.preferred_format:
            parts.append(f"Preferred response format: {self.preferred_format}")
        if self.domains:
            parts.append(f"Domains of interest: {', '.join(self.domains)}")

        if self.custom_rules:
            rules_str = "; ".join(f"{k}: {v}" for k, v in self.custom_rules.items())
            parts.append(f"Custom rules: {rules_str}")

        return "\n".join(parts)

    def merge(self, updates: Dict[str, Any]) -> UserProfile:
        """Create a new profile with updates applied.

        Args:
            updates: Dictionary of fields to update.

        Returns:
            A new UserProfile with the updates merged in.
        """
        current = self.to_dict()
        current.update(updates)
        return UserProfile.from_dict(current)
