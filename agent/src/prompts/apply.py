# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)

from src.prompts.templates import PROMPT_TEMPLATES

# Map LangChain message types to OpenAI-compatible roles
_ROLE_MAP = {
    "human": "user",
    "ai": "assistant",
    "tool": "tool",
    "system": "system",
}


def apply_prompt_template(template_name: str, state: dict) -> list:
    """Build the full message list from the system template and state history.

    The ``prompt`` callable in LangGraph's ``create_react_agent`` **replaces**
    the entire message list with its return value.  We therefore must include
    the complete message history alongside the system prompt, otherwise the
    LLM loses tool-call context after the first interaction.

    Args:
        template_name: Name of the template in PROMPT_TEMPLATES.
        state: The LangGraph state dict (MessagesState).

    Returns:
        A list of message dicts: [system_msg, ...history_msgs...].
    """
    template = PROMPT_TEMPLATES.get(template_name)
    if template is None:
        raise ValueError(f"Unknown prompt template: {template_name}")

    messages = state.get("messages", [])
    result = [{"role": "system", "content": template["system"]}]

    for msg in messages:
        if isinstance(msg, dict):
            result.append(msg)
        elif hasattr(msg, "type"):
            role = _ROLE_MAP.get(msg.type, "user")
            content = msg.content if hasattr(msg, "content") else str(msg)
            result.append({"role": role, "content": content})

    return result
