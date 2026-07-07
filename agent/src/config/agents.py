# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Literal

# Define available LLM types
LLMType = Literal["basic", "reasoning", "vision"]

# Define agent-LLM mapping
AGENT_LLM_MAP: dict[str, LLMType] = {
    "coordinator": "basic",
    "planner": "basic",
    "researcher": "basic",
    "coder": "basic",
    "reporter": "basic",
    "podcast_script_writer": "basic",
    "ppt_composer": "basic",
    "prose_writer": "basic",
    "prompt_enhancer": "reasoning",
    "mcp_test": "basic",
    "ui_test": "basic",
    "case_generate": "basic",
    "case_run": "basic",
    "case_update": "basic",
    "scenario_design": "basic",
    "scenario_generate": "basic",
    "scenario_run": "basic",
    "scenario_fix": "basic",
    "scenario_report": "basic",
}
