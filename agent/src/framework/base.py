"""Sub-agent base class — every pluggable test agent inherits from this."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from langgraph.graph import StateGraph
from langgraph.types import Command

from src.framework.registry import SubAgentDefinition

logger = logging.getLogger(__name__)


class SubAgentBase(ABC):
    """Abstract base for a domain-specific test agent.

    Subclasses **must** implement:

    * ``agent_id`` (class attr) — unique key used in the registry
    * ``name`` / ``description`` (class attrs) — human-readable metadata
    * ``intent_keywords`` (class attr) — keywords for intent matching
    * ``build_graph()`` — wire nodes into a ``StateGraph`` and return it
    * ``get_state_schema()`` — return the TypedDict / BaseModel used as state
    """

    # ── Override these in subclasses ──────────────────────────────────────
    agent_id: str = ""
    name: str = ""
    description: str = ""
    intent_keywords: list[str] = []
    icon: str = "el-icon-document"

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """Build and return a **compiled** LangGraph StateGraph."""
        ...

    @abstractmethod
    def get_state_schema(self) -> type:
        """Return the state type for this sub-agent's graph."""
        ...

    def get_tools(self) -> list:
        """Return tool instances available to this sub-agent.

        Override when the agent needs specific tools.
        """
        return []

    def get_prompts(self) -> dict[str, str]:
        """Return prompt templates used by this sub-agent, keyed by node name.

        Override when the agent defines custom prompts.
        """
        return {}

    # ── Convenience ───────────────────────────────────────────────────────
    def to_definition(self) -> SubAgentDefinition:
        """Convert this class into a ``SubAgentDefinition`` for the registry."""
        return SubAgentDefinition(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            graph=self.build_graph(),
            intent_keywords=self.intent_keywords,
            icon=self.icon,
        )

    def register(self) -> None:
        """Build the graph and register in the global registry."""
        from src.framework.registry import register as _register

        _register(self.to_definition())


def _noop_node(state: dict) -> dict:
    """No-op node — placeholder, does nothing."""
    return state


class PlaceholderAgent(SubAgentBase):
    """A do-nothing sub-agent used during development / testing.

    Provides a single node that immediately returns to the orchestrator.
    """

    agent_id = "placeholder"
    name = "Placeholder"
    description = "Empty sub-agent for testing the framework"
    intent_keywords: list[str] = []

    def build_graph(self) -> StateGraph:
        from langgraph.graph import StateGraph, END

        builder = StateGraph(dict)
        builder.add_node("noop", _noop_node)
        builder.set_entry_point("noop")
        builder.add_edge("noop", END)
        return builder.compile()

    def get_state_schema(self) -> type:
        return dict
