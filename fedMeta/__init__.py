"""FedMeta: Privacy-preserving, dynamic multi-agent system with federated learning."""

__version__ = "0.1.0"

# Lazy imports to avoid circular dependency issues
# Use: from fedMeta import build_meta_agent
# or:  from fedMeta.agent_builder import build_meta_agent

__all__ = ["build_meta_agent", "build_sub_agent", "Settings", "get_settings"]
