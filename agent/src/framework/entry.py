"""AI Test Agent Framework — streaming entry point.

The graph is built by the orchestrator (``src.framework.orchestrator``),
which dynamically discovers sub-agents from the registry.

Topology::

    START
      │
      ▼
    intent_recognition  — LLM classifies intent + keyword match
      │
      ├──(general_chat)──► general_response ──► END
      │
      └──(matched sub-agent)
            │
            ▼
          <sub-agent graph>  ← nested compiled StateGraph
            │                   (events streamed transparently)
            ▼
          END

Sub-agents (discovered via registry):
    - case_gen       → 单接口用例生成
    - scenario_gen   → 场景用例生成
    - code_quality   → 代码质量分析
    - (extensible — register a SubAgentDefinition to add more)
"""

import json
import logging
from typing import AsyncIterator
from src.shared.tools import RECURSION_LIMIT

# Lazy-initialized graph instance
_graph = None

logger = logging.getLogger(__name__)


# ── Node label helpers ─────────────────────────────────────────────────────
def _get_node_labels() -> dict[str, str]:
    """Return node labels from the orchestrator's dynamic registry."""
    from src.framework.orchestrator import get_node_labels
    return get_node_labels()


# ── Graph builders ─────────────────────────────────────────────────────────
async def _build_graph():
    """Build the framework-based graph (orchestrator + registered sub-agents).

    Sub-agents must already be registered (done at FastAPI startup via
    ``server.app.startup``) before the first call to this function.
    """
    from src.framework.orchestrator import build_orchestrator_graph
    from src.framework.checkpoint import aget_checkpointer

    checkpointer = await aget_checkpointer()
    graph = build_orchestrator_graph(checkpointer=checkpointer)
    labels = _get_node_labels()
    logger.info("Graph built, nodes: %s", list(labels.keys()))
    return graph


async def _get_graph():
    """Lazy singleton — builds the graph on first access."""
    global _graph
    if _graph is None:
        _graph = await _build_graph()
    return _graph


# ── Public API ─────────────────────────────────────────────────────────────
async def main(input_text: str, thread_id: str = None):
    """Non-streaming entry point — returns final state."""
    agent_input = {"messages": [__import__("langchain_core.messages").HumanMessage(content=input_text)]}

    from src.utils.langfuse import callback_handler
    config = {}
    if callback_handler:
        config["callbacks"] = callback_handler
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    graph = await _get_graph()
    return await graph.ainvoke(agent_input, config)


async def stream_main(agent_input, config: dict = None) -> AsyncIterator[str]:
    """Streaming entry point — yields SSE events as the graph executes.

    Parameters:
        agent_input: State dict ``{"messages": [...]}`` (new conversation)
                     or ``Command(resume=...)`` (resume interrupted graph).
        config: LangGraph config dict with ``callbacks`` and optionally
                ``configurable.thread_id`` for state persistence.

    SSE event types:
        ``node_start``  — a node begins executing (any nested level)
        ``node_end``    — a node finished, with optional summary
        ``message``     — LLM-generated streaming text chunk
        ``tool_call``   — a tool invocation started
        ``tool_result`` — a tool execution finished
        ``interrupt``   — graph paused, waiting for user input
        ``done``        — workflow completed
        ``error``       — an error occurred
    """
    if config is None:
        config = {}

    from src.utils.langfuse import callback_handler
    if callback_handler:
        config.setdefault("callbacks", callback_handler)
    config.setdefault("recursion_limit", RECURSION_LIMIT)

    graph = await _get_graph()

    # Track the currently-executing orchestrator node so that tool calls
    # inside nested sub-graphs (React agents) are attributed to the right
    # workflow node instead of the internal "tools" node name.
    _current_node: str = ""

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _tool_node() -> str:
        """Resolve the orchestrator node for the current tool call.

        Uses the tracked orchestrator node when available (tools inside
        nested React agents), falling back to the raw langgraph_node
        from the event metadata.
        """
        return _current_node or ""

    try:
        async for event in graph.astream_events(agent_input, config, version="v2"):
            kind = event["event"]
            raw_node = event.get("metadata", {}).get("langgraph_node", "")

            # ── Node lifecycle ──────────────────────────────────────
            if kind == "on_chain_start":
                node_name = event.get("name", "")
                labels = _get_node_labels()
                if node_name in labels:
                    _current_node = node_name
                    yield _sse("node_start", {
                        "node": node_name,
                        "label": labels[node_name],
                    })

            elif kind == "on_chain_end":
                node_name = event.get("name", "")
                labels = _get_node_labels()
                if node_name in labels:
                    if _current_node == node_name:
                        _current_node = ""
                    output = event.get("data", {}).get("output", {})
                    messages = output.get("messages", []) if isinstance(output, dict) else []
                    msg_text = ""
                    if messages:
                        last = messages[-1]
                        if hasattr(last, "content"):
                            msg_text = last.content
                        elif isinstance(last, dict):
                            msg_text = last.get("content", "")
                    yield _sse("node_end", {
                        "node": node_name,
                        "label": labels[node_name],
                        "summary": msg_text[:500] if msg_text else "",
                    })

            # ── LLM streaming tokens ────────────────────────────────
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield _sse("message", {
                        "content": chunk.content,
                        "node": _current_node or raw_node,
                    })

            # ── Tool calls ──────────────────────────────────────────
            elif kind == "on_tool_start":
                yield _sse("tool_call", {
                    "tool": event.get("name", "unknown"),
                    "status": "start",
                    "node": _current_node or raw_node,
                })
            elif kind == "on_tool_end":
                output = event.get("data", {}).get("output")
                if hasattr(output, "model_dump"):
                    result = output.model_dump()
                elif hasattr(output, "dict"):
                    result = output.dict()
                else:
                    result = output
                yield _sse("tool_result", {
                    "tool": event.get("name", "unknown"),
                    "status": "end",
                    "result": result,
                    "node": _current_node or raw_node,
                })

            # ── LangGraph interrupt (human-in-the-loop) ─────────────
            elif (kind == "on_chain_stream"
                  and event.get("name") == "LangGraph"
                  and isinstance(event.get("data", {}).get("chunk"), dict)
                  and "__interrupt__" in event.get("data", {}).get("chunk", {})):
                interrupt_state = await graph.aget_state(config)
                if interrupt_state is not None and interrupt_state.interrupts:
                    for interrupt_def in interrupt_state.interrupts:
                        interrupt_value = interrupt_def.value
                        logger.info(
                            "Graph interrupted (thread=%s): %s",
                            config.get("configurable", {}).get("thread_id", "default"),
                            str(interrupt_value)[:200],
                        )
                        yield _sse("interrupt", {
                            "type": interrupt_value.get("type", "select_apis") if isinstance(interrupt_value, dict) else "select_apis",
                            "data": interrupt_value if isinstance(interrupt_value, dict) else {"payload": str(interrupt_value)},
                        })
                return  # Graph is paused — don't emit "done"

        # ── Fallback: check checkpoint state for undetected interrupts ──
        state = await graph.aget_state(config)
        if state is not None and state.interrupts:
            for interrupt_def in state.interrupts:
                interrupt_value = interrupt_def.value
                logger.info(
                    "Interrupt detected via get_state (thread=%s): %s",
                    config.get("configurable", {}).get("thread_id", "default"),
                    str(interrupt_value)[:200],
                )
                yield _sse("interrupt", {
                    "type": interrupt_value.get("type", "select_apis") if isinstance(interrupt_value, dict) else "select_apis",
                    "data": interrupt_value if isinstance(interrupt_value, dict) else {"payload": str(interrupt_value)},
                })
            return

        yield _sse("done", {"status": "completed"})

    except Exception as e:
        logger.error("Stream error: %s", e, exc_info=True)
        yield _sse("error", {"status": "error", "message": str(e)})
