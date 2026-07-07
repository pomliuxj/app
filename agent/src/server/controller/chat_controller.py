# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from src.server.request_model.chat_request import ChatRequest, ChatMessage
from src.framework.entry import stream_main

logger = logging.getLogger(__name__)


def _extract_text(msg: ChatMessage) -> str:
    """Extract plain text from a ChatMessage (content may be str or list[ContentItem])."""
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(item.text for item in content if getattr(item, "text", None))
    return str(content)



router = APIRouter()


@router.post("/api/chat/test_case")
async def test_case(request: ChatRequest):
    """Generate and execute AI-driven automated test cases (SSE streaming).

    Two modes of operation, distinguished by the presence of ``selection``:

    **First request** (selection is None / empty):
        Starts a new test-case generation workflow.
        Orchestrates: intent_recognition → select_apis → [interrupt] →
        case_generate → case_run → case_update → final_report.

    **Resume request** (selection is present):
        Resumes a previously interrupted graph.  The ``selection`` value
        is the user-chosen API list and is passed to the graph via
        ``Command(resume=selection)``.  The same ``thread_id`` must be
        used so LangGraph can find the paused state.

    Returns SSE event stream:
        node_start  — a graph node begins
        message     — LLM text chunk
        tool_call   — tool invocation started
        tool_result — tool execution finished, with the return value
        node_end    — node finished with summary
        interrupt   — graph paused, waiting for user input
        done        — workflow complete
        error       — exception details
    """
    config = {"configurable": {"thread_id": request.thread_id or "__default__"}}

    # ── Resume mode: scenario confirm ─────────────────────────────────
    if request.scenario_confirm:
        logger.info(
            "Resuming graph (thread=%s) with scenario confirmation: %s",
            request.thread_id, request.scenario_confirm.get("action", "unknown"),
        )
        resume_cmd = Command(resume=request.scenario_confirm)
        return StreamingResponse(
            stream_main(resume_cmd, config),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Resume mode: user is responding to an API selection interrupt ──
    if request.selection:
        logger.info(
            "Resuming graph (thread=%s) with %d selected APIs",
            request.thread_id, len(request.selection),
        )
        resume_cmd = Command(resume=request.selection)
        return StreamingResponse(
            stream_main(resume_cmd, config),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── First-request mode: start a new conversation ──────────────────
    messages = request.messages or []
    user_msgs = [m for m in messages if m.role == "user"]
    if not user_msgs:
        return StreamingResponse(
            iter(["event: error\ndata: {\"message\":\"至少需要一条用户消息\"}\n\n"]),
            media_type="text/event-stream",
        )

    input_text = _extract_text(user_msgs[-1])

    agent_input = {"messages": [HumanMessage(content=input_text)]}

    return StreamingResponse(
        stream_main(agent_input, config),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
