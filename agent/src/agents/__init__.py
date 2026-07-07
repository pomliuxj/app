# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# ── Lazy export to avoid circular import ──────────────────────────────
def __getattr__(name):
    if name == "create_agent":
        from .agents import create_agent as _create_agent
        return _create_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# ── Pluggable sub-agent modules ──────────────────────────────────────────
# Each sub-agent module registers itself with the framework on import.
from src.agents import case_gen  # noqa: F401
from src.agents import scenario_gen  # noqa: F401
from src.agents import code_quality  # noqa: F401

__all__ = ["create_agent"]
