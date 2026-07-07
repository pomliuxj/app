# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import os
import yaml
from typing import Dict, Any
import logging
logger = logging.getLogger(__name__)

def replace_env_vars(value: str) -> str:
    """Replace environment variables in string values."""
    if not isinstance(value, str):
        return value
    if value.startswith("$"):
        env_var = value[1:]
        return os.getenv(env_var, env_var)
    return value


def process_dict(config: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively process dictionary to replace environment variables."""
    if not config:
        return {}
    result = {}
    for key, value in config.items():
        if isinstance(value, dict):
            result[key] = process_dict(value)
        elif isinstance(value, str):
            result[key] = replace_env_vars(value)
        else:
            result[key] = value
    return result


_config_cache: Dict[str, Dict[str, Any]] = {}


def get_config_file_path() -> str:
    """Get the path to the configuration file."""
    from pathlib import Path
    config_path = os.environ.get('CONFIG_FILE_PATH')
    if config_path and Path(config_path).exists():
        return config_path
    app_env = os.environ.get("ENV", os.environ.get("APP_ENV", "dev")).lower()
    return str((Path(__file__).resolve().parent.parent.parent / f"conf_{app_env}.yaml"))


def load_yaml_config(file_path: str) -> Dict[str, Any]:
    """Load and process YAML configuration file."""
    # 如果文件不存在，返回{}
    logger.info(f"Loading YAML config from {file_path}...")
    if not os.path.exists(file_path):
        return {}

    # 检查缓存中是否已存在配置
    if file_path in _config_cache:
        return _config_cache[file_path]

    # 如果缓存中不存在，则加载并处理配置
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    processed_config = process_dict(config)

    # 将处理后的配置存入缓存
    _config_cache[file_path] = processed_config
    return processed_config
