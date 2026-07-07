"""Shared utilities — framework-level helpers used by both agent and Django.

These are **pure functions** with no Django ORM dependency.
"""

from src.shared.json_utils import check_json, get_json

__all__ = ["check_json", "get_json"]
