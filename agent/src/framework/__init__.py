"""Test Agent Framework — orchestrator + registry + sub-agent base.

Quick start::

    from src.framework import (
        SubAgentBase, SubAgentDefinition, register_sub_agent,
        build_orchestrator_graph, get_checkpointer,
    )
"""

from src.framework.registry import (
    SubAgentDefinition,
    register as register_sub_agent,
    get as get_sub_agent,
    list_all as list_sub_agents,
    match_by_keywords,
)
from src.framework.base import SubAgentBase, PlaceholderAgent
from src.framework.orchestrator import (
    build_orchestrator_graph,
    IntentClassification,
)
from src.framework.checkpoint import aget_checkpointer

__all__ = [
    "SubAgentBase",
    "SubAgentDefinition",
    "PlaceholderAgent",
    "register_sub_agent",
    "get_sub_agent",
    "list_sub_agents",
    "match_by_keywords",
    "build_orchestrator_graph",
    "IntentClassification",
    "aget_checkpointer",
]
