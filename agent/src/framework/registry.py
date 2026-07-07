"""Sub-agent registry — the single extension point for adding new test agents.

To add a new sub-agent::

    1. Create a directory under ``agents/`` with graph + nodes + prompts
    2. Define a SubAgentDefinition
    3. Call ``register(my_definition)``

The orchestrator discovers available sub-agents via this registry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from langgraph.graph import StateGraph

logger = logging.getLogger(__name__)


@dataclass
class SubAgentDefinition:
    """Blueprint for a pluggable sub-agent."""

    agent_id: str
    """Unique key, e.g. ``"case_gen"``, ``"scenario_gen"``."""

    name: str
    """Human-readable label for UI display."""

    description: str
    """One-paragraph summary of what this agent does."""

    graph: StateGraph
    """Compiled LangGraph sub-graph (nodes + edges already wired up)."""

    intent_keywords: list[str] = field(default_factory=list)
    """Chinese / English keywords that hint this agent should be selected.

    Example: ``["用例生成", "测试用例", "test case", "接口测试"]``.
    """

    # ── Additional metadata ──────────────────────────────────────────
    icon: str = "el-icon-document"
    """Frontend icon hint."""

    interruptible: bool = True
    """Whether this sub-agent may call ``interrupt()`` during execution."""

    node_labels: dict[str, str] = field(default_factory=dict)
    """Chinese display labels for this sub-agent's internal nodes.

    Example: ``{"select_apis": "选取接口", "case_generate": "生成用例", ...}``.
    Used by the orchestrator to provide human-readable node names in SSE events.
    """


# ── Global registry ────────────────────────────────────────────────────────
_SUB_AGENTS: dict[str, SubAgentDefinition] = {}


def register(definition: SubAgentDefinition) -> None:
    """Register a sub-agent so the orchestrator can route to it."""
    if definition.agent_id in _SUB_AGENTS:
        logger.warning(
            "Sub-agent '%s' is being overwritten (id='%s')",
            definition.name,
            definition.agent_id,
        )
    _SUB_AGENTS[definition.agent_id] = definition
    logger.info(
        "Registered sub-agent '%s' (id=%s, keywords=%s)",
        definition.name,
        definition.agent_id,
        definition.intent_keywords,
    )


def get(agent_id: str) -> Optional[SubAgentDefinition]:
    """Look up a sub-agent by id."""
    return _SUB_AGENTS.get(agent_id)


def list_all() -> dict[str, SubAgentDefinition]:
    """Return a copy of the full registry."""
    return dict(_SUB_AGENTS)


def match_by_keywords(user_input: str) -> Optional[str]:
    """Simple keyword-based matching — fast pre-filter before LLM intent detection.

    Returns the ``agent_id`` of the first sub-agent whose keywords match, or
    ``None`` when no keyword hits.
    """
    if not user_input:
        return None
    text = user_input.lower()
    for agent_id, defn in _SUB_AGENTS.items():
        if any(kw.lower() in text for kw in defn.intent_keywords):
            return agent_id
    return None
