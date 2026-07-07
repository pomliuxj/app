# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from enum import Enum


class ReportStyle(str, Enum):
    """Report style enum."""
    SUMMARY = "summary"
    GENERAL = "general"
    ACADEMIC = "academic"
