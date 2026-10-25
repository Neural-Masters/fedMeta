"""Main agent builder for FedMeta.

Builds Meta-Agent and sub-agents with profile adaptation,
API tool integration, and learning machine configuration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import os
from fedMeta.config import get_settings
from fedMeta.learning.behavior_adapter import BehaviorAdapter
from fedMeta.learning.shared_knowledge import SharedKnowledgeManager
from fedMeta.profile.manager import ProfileManager
from fedMeta.profile.models import UserProfile
from fedMeta.tools.api_tool_registry import APIToolRegistry
from fedMeta.tools.executor import APIToolExecutor
from agno.models.openai import OpenAIResponses, OpenAIChat
from agno.models.nvidia import Nvidia
from agno.models.mistral import MistralChat
from agno.models.groq import Groq

logger = logging.getLogger(__name__)

# LLM for reasoning (NVIDIA-hosted deepseek, configurable via .env)
LLM = Groq(
    api_key=os.getenv("GROQ_API"),
    id=os.getenv("NVIDIA_LLM_MODEL"),
)

# Default system prompt for the Meta-Agent
DEFAULT_META_PROMPT = """You are the FedMeta Orchestrator, a meta-agent that dynamically
generates specialized sub-agents to solve complex, personalized tasks.

Your capabilities:
1. Analyze user intent and decompose complex tasks
2. Spawn specialized sub-agents with tailored tools and instructions
3. Adapt behavior based on user profiles and preferences
4. Learn from interactions to improve over time
5. Share sanitized insights via federated learning

Always respect user privacy. Never share raw user data.
Adapt your communication style to match the user's profile.

Use the registered API tools directly whenever they fit the request. For a web
search or current-information request, call the user's web-search API tool
before answering; do not merely describe how you would search. Delegate to a
sub-agent only for complex or multi-step tasks. If a tool returns an error,
explain that honestly rather than claiming the call succeeded.

Use search_my_learnings to recall this user's private saved notes, and
search_learnings for reusable global knowledge. Use the FedMeta save_learning
tool to retain an insight privately. Set share_globally=true only when the user
explicitly asks to share that generalized insight with other users; never share
personal preferences, identifiers, private task details, raw prompts, or tool
output. Provide an evidence-based confidence score from 0 to 1; items below the
configured federation threshold remain private.
"""

DEFAULT_SUB_AGENT_PROMPT = """You are a specialized sub-agent spawned by the FedMeta Orchestrator.
Complete the assigned task efficiently and return results.
Follow the user's communication preferences and expertise level.
"""


def build_meta_agent(
    model: Any = None,
    db: Any = None,
    user_id: Optional[str] = None,
    instructions: Optional[str] = None,
    tools: Optional[List] = None,
    behavior_adapter: Optional[BehaviorAdapter] = None,
    shared_knowledge_manager: Optional[SharedKnowledgeManager] = None,
    **kwargs: Any,
) -> Any:
    """Build the Meta-Agent with full profile adaptation.

    The Meta-Agent is the orchestrator that spawns sub-agents and
    coordinates task execution.  It includes the Learning Machine
    for continuous improvement and profile-based personalization.

    Args:
        model: LLM model instance (OpenAIResponses, etc.).
        db: Database instance for the agent.
        user_id: Optional default user_id for this agent instance.
        instructions: Custom system instructions.
        tools: Additional base tools for the agent.
        behavior_adapter: BehaviorAdapter instance.
        shared_knowledge_manager: SharedKnowledgeManager instance.
        **kwargs: Additional keyword arguments passed to Agent().

    Returns:
        Configured Agno Agent instance.
    """
    from agno.agent import Agent
    from agno.learn import (
        LearningMachine,
        LearningMode,
        UserProfileConfig,
        UserMemoryConfig,
    )
    from agno.db.postgres import PostgresDb

    settings = get_settings()

    # PostgreSQL so session history + learnings persist across server restarts
    # (schema "ai" houses Agno system tables; our app tables live in public).
    if db is None:
        db = PostgresDb(
            db_url=settings.database_url,
            session_table="agno_sessions",
            runs_table="agno_runs",
            learnings_table="agno_learnings_store",
            db_schema="ai",
        )

    # Initialize components
    behavior_adapter = behavior_adapter or BehaviorAdapter()
    shared_knowledge_manager = shared_knowledge_manager or SharedKnowledgeManager()

    # Build personalized instructions
    base_instructions = instructions or DEFAULT_META_PROMPT
    if user_id:
        system_prompt = behavior_adapter.build_personalized_prompt(
            user_id=user_id,
            base_instructions=base_instructions,
        )
    else:
        system_prompt = base_instructions

    # Get relevant tools for the meta-agent
    base_tools = tools or []
    meta_tools = list(base_tools)

    # Add sub-agent spawning tool
    meta_tools.append(create_sub_agent_spawner(user_id, behavior_adapter))
    if user_id:
        # Add account tools directly to the orchestrator so simple API tasks
        # can execute without requiring a sub-agent tool call first.
        meta_tools.extend(behavior_adapter.get_available_tools_for_user(user_id, limit=10))

    # Get learning machine configuration
    learning_config: Dict[str, Any] = {}
    learned_knowledge_store = None
    if user_id:
        config = behavior_adapter.get_learning_config(user_id)

        if config.get("user_profile", {}).get("enabled"):
            learning_config["user_profile"] = UserProfileConfig(
                mode=LearningMode.AGENTIC
                if config["user_profile"].get("mode") == "agentic"
                else LearningMode.ALWAYS,
            )

        if config.get("user_memory", {}).get("enabled"):
            learning_config["user_memory"] = UserMemoryConfig(
                mode=LearningMode.AGENTIC
                if config["user_memory"].get("mode") == "agentic"
                else LearningMode.ALWAYS,
            )

        # Tracks goal/plan/progress; replaced each run, keeps long tasks on thread
        if config.get("session_context", {}).get("enabled"):
            learning_config["session_context"] = True

        if config.get("learned_knowledge", {}).get("enabled"):
            try:
                from agno.learn.stores import LearnedKnowledgeStore

                # Agno's native search tool is retained, but its unconstrained
                # save tool is disabled. FedMeta supplies a save tool requiring
                # explicit federation consent and a confidence score.
                learned_config = shared_knowledge_manager.get_learned_knowledge_config()
                learned_config.knowledge = shared_knowledge_manager.get_knowledge()
                learned_config.agent_can_save = False
                learned_config.agent_can_search = True
                learned_knowledge_store = LearnedKnowledgeStore(config=learned_config)

                learning_config["db"] = db
                learning_config["knowledge"] = shared_knowledge_manager.get_knowledge()
                learning_config["learned_knowledge"] = learned_knowledge_store

                learned_knowledge_store.fedmeta_pending_candidates = []
                meta_tools.append(
                    create_federated_learning_tool(learned_knowledge_store, user_id)
                )
                meta_tools.append(create_private_learning_search_tool(learned_knowledge_store, user_id))
            except (ImportError, Exception) as e:
                logger.warning("Could not configure learned knowledge: %s", e)

    # Build the agent
    agent = Agent(
        name="FedMeta Orchestrator",
        model=LLM,
        db=db,
        user_id=user_id,
        # Persist per-user session so chat history carries across requests
        session_id=f"session_{user_id}" if user_id else None,
        instructions=system_prompt,
        tools=meta_tools,
        learning=LearningMachine(**learning_config) if learning_config else None,
        add_datetime_to_context=True,
        add_history_to_context=True,
        num_history_runs=5,
        add_learnings_to_context=True,
        offload_tool_results=True,
        **kwargs,
    )

    # The API endpoint consumes these explicit candidate objects after the run;
    # there is deliberately no observer that exports conversation messages.
    agent.fedmeta_learned_knowledge_store = learned_knowledge_store

    logger.info("Meta-Agent built successfully (user_id=%s)", user_id)
    return agent


def create_federated_learning_tool(learned_store: Any, user_id: str) -> Any:
    """Create guarded local-save tool, optionally marking an item for sharing.

    The actual federated network operation happens after the Agno run returns,
    so retries and privacy filtering are handled by the durable outbox.
    """

    def save_learning(
        title: str,
        learning: str,
        confidence: float,
        context: Optional[str] = None,
        tags: Optional[List[str]] = None,
        share_globally: bool = False,
    ) -> str:
        """Save a reusable insight locally and optionally federate it.

        Args:
            title: Short, generic title without personal or confidential details.
            learning: Reusable rule or insight, not conversation text.
            confidence: Evidence-based confidence from 0.0 to 1.0.
            context: Optional generic applicability context (no user-specific data).
            tags: Short generic categories.
            share_globally: Set true only when the user explicitly requests
                anonymous sharing with other FedMeta users.
        """
        if not 0.0 <= confidence <= 1.0:
            return "Confidence must be between 0 and 1; nothing was saved."

        saved = learned_store.save(
            title=title,
            learning=learning,
            context=context,
            tags=tags,
            user_id=user_id,
            namespace="user",
        )
        if not saved:
            return "Could not save this learning to your private Agno knowledge store."

        threshold = get_settings().confidence_threshold
        if share_globally and confidence >= threshold:
            globally_saved = learned_store.save(
                title=title,
                learning=learning,
                context=context,
                tags=tags,
                namespace="global",
            )
            if not globally_saved:
                return "Saved to your private memory, but it could not be added to the local global-knowledge index. Nothing was federated."
            learned_store.fedmeta_pending_candidates.append(
                {
                    "title": title,
                    "learning": learning,
                    "context": context,
                    "tags": tags or [],
                    "confidence": confidence,
                }
            )
            return "Saved locally and queued for anonymous federation after this run."
        if share_globally:
            return (
                f"Saved to your private memory only; confidence {confidence:.2f} is below the "
                f"federation threshold {threshold:.2f}."
            )
        return "Saved to your private memory only; no learning was sent to the federation server."

    save_learning.__name__ = "save_learning"
    return save_learning


def create_private_learning_search_tool(learned_store: Any, user_id: str) -> Any:
    """Search only the signed-in user's private LearnedKnowledge namespace."""

    def search_my_learnings(query: str, limit: int = 5) -> str:
        """Search this user's private saved notes; never searches other users' notes.

        Args:
            query: What private note or preference to recall.
            limit: Maximum results to return (1-10).
        """
        import json

        results = learned_store.search(
            query=query,
            user_id=user_id,
            namespace="user",
            limit=max(1, min(int(limit), 10)),
        )
        return json.dumps(
            [
                {
                    "title": getattr(item, "title", ""),
                    "learning": getattr(item, "learning", ""),
                    "context": getattr(item, "context", None),
                    "tags": getattr(item, "tags", []) or [],
                }
                for item in results
            ],
            ensure_ascii=False,
        )

    search_my_learnings.__name__ = "search_my_learnings"
    return search_my_learnings


def build_sub_agent(
    task_description: str,
    model: Any = None,
    db: Any = None,
    user_id: Optional[str] = None,
    tools: Optional[List] = None,
    behavior_adapter: Optional[BehaviorAdapter] = None,
    instructions: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Build a specialized sub-agent for a specific task.

    Sub-agents are spawned by the Meta-Agent and are tailored to
    the specific task at hand, with tools selected based on relevance
    and user profile.

    Args:
        task_description: Description of the task to accomplish.
        model: LLM model instance.
        db: Database instance.
        user_id: User identifier for profile adaptation.
        tools: Additional task-specific tools.
        behavior_adapter: BehaviorAdapter instance.
        instructions: Custom instructions.
        **kwargs: Additional keyword arguments.

    Returns:
        Configured Agno Agent instance.
    """
    from agno.agent import Agent
    from agno.db.postgres import PostgresDb

    behavior_adapter = behavior_adapter or BehaviorAdapter()

    settings = get_settings()

    if db is None:
        db = PostgresDb(
            db_url=settings.database_url,
            session_table="agno_sessions",
            runs_table="agno_runs",
            db_schema="ai",
        )

    # Select relevant tools for this task
    task_tools = behavior_adapter.select_tools_for_task(
        task_context=task_description,
        user_id=user_id,
        limit=5,
    )

    if tools:
        task_tools.extend(tools)

    # Build instructions
    base_instructions = instructions or DEFAULT_SUB_AGENT_PROMPT
    if user_id:
        system_prompt = behavior_adapter.build_personalized_prompt(
            user_id=user_id,
            base_instructions=base_instructions,
        )
    else:
        system_prompt = base_instructions

    agent = Agent(
        name=f"Sub-Agent: {task_description[:50]}",
        model=LLM,
        db=db,
        user_id=user_id,
        session_id=f"subagent_{user_id}" if user_id else None,
        instructions=system_prompt,
        tools=task_tools,
        add_datetime_to_context=True,
        add_history_to_context=True,
        num_history_runs=3,
        **kwargs,
    )

    logger.info("Sub-agent built for task: %s", task_description[:80])
    return agent


def create_sub_agent_spawner(parent_user_id: Optional[str], behavior_adapter: BehaviorAdapter) -> Any:
    """Create a tool function that allows the Meta-Agent to spawn sub-agents.

    Args:
        parent_user_id: The requesting user's id (inherited by the sub-agent).
        behavior_adapter: The behavior adapter instance.

    Returns:
        A callable tool function for Agno.
    """

    def spawn_sub_agent(
        task_description: str,
        instructions: Optional[str] = None,
        tools: Optional[List] = None,
    ) -> str:
        """Spawn a specialized sub-agent for a specific task.

        Args:
            task_description: Description of what the sub-agent should do.
            instructions: Optional custom instructions for the sub-agent.
            tools: Optional list of tools to provide.

        Returns:
            The sub-agent's answer text.
        """
        sub_agent = build_sub_agent(
            task_description=task_description,
            user_id=parent_user_id,
            instructions=instructions,
            tools=tools,
            behavior_adapter=behavior_adapter,
        )

        # Execute the sub-agent with the task description
        result = sub_agent.run(task_description)
        content = getattr(result, "content", None)
        return content if isinstance(content, str) else str(result)

    spawn_sub_agent.__name__ = "spawn_sub_agent"
    spawn_sub_agent.__doc__ = "Spawn a specialized sub-agent for a specific task. Provide a clear, self-contained task_description describing exactly what the sub-agent should accomplish and return."

    return spawn_sub_agent
