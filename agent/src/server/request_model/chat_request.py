# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import List, Optional, Union

from pydantic import BaseModel, Field


class ContentItem(BaseModel):
    type: str = Field(..., description="The type of content (text, image, etc.)")
    text: Optional[str] = Field(None, description="The text content if type is 'text'")
    image_url: Optional[str] = Field(
        None, description="The image URL if type is 'image'"
    )

class ChatMessage(BaseModel):
    role: str = Field(
        ..., description="The role of the message sender (user or assistant)"
    )
    content: Union[str, List[ContentItem]] = Field(
        ...,
        description="The content of the message, either a string or a list of content items",
    )

class ChatRequest(BaseModel):
    messages: Optional[List[ChatMessage]] = Field(
        [], description="History of messages between the user and the assistant"
    )

    thread_id: Optional[str] = Field(
        "__default__", description="A specific conversation identifier"
    )

    interrupt_feedback: Optional[str] = Field(
        None, description="Interrupt feedback from the user on the plan"
    )

    enable_deep_thinking: Optional[bool] = Field(
        False, description="Whether to enable deep thinking"
    )

    selection: Optional[list] = Field(
        None, description="User's selected API list — when present, resume the "
                          "paused graph with Command(resume=selection) instead "
                          "of starting a new conversation"
    )

    scenario_confirm: Optional[dict] = Field(
        None, description="Scenario confirmation payload — when present, resume "
                          "the paused graph with Command(resume=scenario_confirm). "
                          "Used for the scenario_design interrupt confirmation."
    )