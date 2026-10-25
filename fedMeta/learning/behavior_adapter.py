"""Behavior Adapter: bridges user profiles with agent behavior.

Integrates with Agno's LearningMachine to:
- Inject user profile context into agent system prompts
- Select relevant tools based on profile + task context
- Configure learning stores (user_profile, user_memory, learned_knowledge, session_context)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fedMeta.profile.manager import ProfileManager
from fedMeta.profile.models import UserProfile
from fedMeta.tools.api_tool_registry import APIToolRegistry
from fedMeta.tools.executor import APIToolExecutor

logger = logging.getLogger(__name__)


class BehaviorAdapter:
    """Adapts agent behavior based on user profile and context.

    This is the core component that connects the profile system,
    tool registry, and learning machine together to produce
    personalized agent behavior.
    """

    def __init__(
        self,
        profile_manager: Optional[ProfileManager] = None,
        tool_registry: Optional[APIToolRegistry] = None,
        tool_executor: Optional[APIToolExecutor] = None,
    ) -> None:
        self.profile_manager = profile_manager or ProfileManager()
        self.tool_registry = tool_registry or APIToolRegistry()
        self.tool_executor = tool_executor or APIToolExecutor()

    def build_personalized_prompt(
        self,
        user_id: str,
        base_instructions: str,
    ) -> str:
        """Build a personalized system prompt by injecting profile context.

        Args:
            user_id: The user's unique identifier.
            base_instructions: The base system instructions.

        Returns:
            The augmented system prompt with profile context.
        """
        profile = self.profile_manager.get_profile(user_id)
        if profile is None:
            logger.debug("No profile found for user_id=%s, using base prompt", user_id)
            return base_instructions

        profile_context = profile.to_prompt_context()
        personalized = f"""{base_instructions}

<user_profile>
{profile_context}
</user_profile>

Adapt your responses to match the user's expertise level, communication style, and preferred format."""

        logger.debug("Built personalized prompt for user_id=%s", user_id)
        return personalized

    def select_tools_for_task(
        self,
        task_context: str,
        user_id: Optional[str] = None,
        limit: int = 5,
    ) -> List:
        """Select relevant tools based on task context and user profile.

        Args:
            task_context: Description of the current task.
            user_id: Optional user_id for profile-based filtering.
            limit: Maximum number of tools to return.

        Returns:
            List of callable tool functions.
        """
        # Enhance task context with user profile domains
        enhanced_context = task_context
        if user_id:
            profile = self.profile_manager.get_profile(user_id)
            if profile and profile.domains:
                domains_str = " ".join(profile.domains)
                enhanced_context = f"{task_context} {domains_str}"

        # Find relevant tools from registry
        relevant_endpoints = self.tool_registry.find_relevant_tools(
            task_context=enhanced_context,
            limit=limit,
            owner_user_id=user_id,
        )

        # Wrap into callable functions
        tool_functions = self.tool_executor.create_tool_functions(relevant_endpoints)
        logger.info(
            "Selected %d tools for task (user_id=%s)",
            len(tool_functions),
            user_id,
        )
        return tool_functions

    def get_available_tools_for_user(self, user_id: str, limit: int = 10) -> List[Any]:
        """Return this user's active API tools as Agno Python-backed Functions.

        These tools are attached to the Meta-Agent itself so simple requests
        (for example, web search) do not depend on the model first spawning a
        sub-agent. Sub-agents still get task-relevant tools separately.
        """
        endpoints = self.tool_registry.list_tools(
            active_only=True,
            owner_user_id=user_id,
        )[:limit]
        functions = self.tool_executor.create_tool_functions(endpoints)
        logger.info("Loaded %d account API tools for user_id=%s", len(functions), user_id)
        return functions

    def get_learning_config(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        namespace: str = "global",
    ) -> Dict[str, Any]:
        """Generate LearningMachine configuration for a user session.

        Args:
            user_id: The user's unique identifier.
            session_id: Optional session identifier.
            namespace: Knowledge namespace for shared learnings.

        Returns:
            Dictionary with learning store configuration.
        """
        profile = self.profile_manager.get_profile(user_id)

        config: Dict[str, Any] = {
            "user_profile": {
                "enabled": True,
                "mode": "agentic",
            },
            "user_memory": {
                "enabled": True,
                "mode": "agentic",
            },
            "session_context": {
                "enabled": True,
            },
            "learned_knowledge": {
                "enabled": True,
                "mode": "agentic",
                "namespace": namespace,
            },
        }

        if profile:
            # Customize based on expertise level
            if profile.expertise_level == "beginner":
                config["user_profile"]["mode"] = "always"
            elif profile.expertise_level == "expert":
                config["user_memory"]["mode"] = "always"

        logger.debug("Generated learning config for user_id=%s", user_id)
        return config

    def adapt_agent_instructions(
        self,
        base_instructions: str,
        user_id: str,
        task_type: Optional[str] = None,
    ) -> str:
        """Adapt agent instructions based on user profile and task type.

        Args:
            base_instructions: Base system instructions.
            user_id: The user's identifier.
            task_type: Optional task type for specialized adaptation.

        Returns:
            Adapted instructions string.
        """
        prompt = self.build_personalized_prompt(user_id, base_instructions)

        if task_type:
            profile = self.profile_manager.get_profile(user_id)
            if profile and profile.custom_rules:
                task_rule = profile.custom_rules.get(f"task_{task_type}")
                if task_rule:
                    prompt += f"\n\nTask-specific rule: {task_rule}"

        return prompt

    def close(self) -> None:
        """Close all managed resources."""
        self.profile_manager.close()
        self.tool_registry.close()
