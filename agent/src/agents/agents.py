import logging
from typing import List, Optional, Tuple, Union

from langgraph.prebuilt import create_react_agent
from langgraph.utils.runnable import RunnableLike
from pydantic import BaseModel

from src.prompts import apply_prompt_template
from src.llms.llm import get_llm_by_type
from src.config.agents import AGENT_LLM_MAP

logger = logging.getLogger(__name__)

# StructuredResponseSchema is the type expected by create_react_agent's response_format
StructuredResponseSchema = Union[dict, type[BaseModel], BaseModel]


async def create_agent(
    agent_name: str,
    agent_type: str,
    prompt_template: str,
    tools: Optional[List] = None,
    post_model_hook: Optional[RunnableLike] = None,
    output_format: Union[
        StructuredResponseSchema,
        Tuple[str, StructuredResponseSchema],
    ] = None,
):
    """Factory function to create agents for AI test case generation.

    Args:
        output_format: Either a Pydantic model / JSON schema / TypedDict for
            structured output, OR a tuple of (system_prompt, schema) where the
            system_prompt is injected into the structured-response generation
            call to guide the model.  Using the tuple form helps when the model
            misinterprets the output shape (e.g. returns an array instead of an
            object).

    Note: When setting output_format, streaming must be disabled on the LLM.
    """
    if tools is None:
        tools = []

    base_model = get_llm_by_type(AGENT_LLM_MAP[agent_type])
    return create_react_agent(
        name=agent_name,
        model=base_model,
        tools=tools,
        prompt=lambda state: apply_prompt_template(prompt_template, state),
        post_model_hook=post_model_hook,
        response_format=output_format,
    )
