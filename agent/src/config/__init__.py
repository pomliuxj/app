# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from .loader import load_yaml_config, get_config_file_path
from .questions import BUILT_IN_QUESTIONS, BUILT_IN_QUESTIONS_ZH_CN
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Load YAML configuration (LLM models, etc.)
YAML_CONFIG = load_yaml_config(get_config_file_path())

__all__ = [
    "load_yaml_config",
    "YAML_CONFIG",
    "BUILT_IN_QUESTIONS",
    "BUILT_IN_QUESTIONS_ZH_CN",
]
