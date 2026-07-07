"""Pure JSON comparison and extraction utilities — no Django dependency.

Used by both the agent framework and the Django REST API.
"""

from __future__ import annotations

import json as _json
import logging
import re

logger = logging.getLogger(__name__)

# ── Step reference regex (shared with common.py) ───────────────────────────
_STEP_REF_RE = re.compile(r'^\$(\d+)\.(.+)$')
_SUB_STEP_REF_RE = re.compile(r'\$(\d+)\.([\w.\[\]]+)')


def check_json(src_data, dst_data, checkType):
    """Validate *dst_data* (actual response) against *src_data* (expected).

    Args:
        src_data: Expected value from the test-case definition.
        dst_data: Actual value extracted from the API response.
        checkType: One of ``"equal"``, ``"contain"``, ``"gte"``, ``"lte"``,
                   ``"notNull"``.

    Returns:
        ``True`` when the check passes.
    """
    result = True
    try:
        if checkType == 'equal':
            if isinstance(src_data, dict):
                if len(src_data.keys()) != len(dst_data.keys()):
                    result = False
                    return result
                for key in src_data.keys():
                    if key in dst_data.keys() and result:
                        check_json(src_data[key], dst_data[key], checkType='equal')
                    else:
                        result = False
                        return result
            elif isinstance(src_data, list):
                if len(src_data) == len(dst_data):
                    for src, dst in zip(sorted(src_data), sorted(dst_data)):
                        if result:
                            check_json(src, dst, checkType='equal')
                else:
                    result = False
                    return result
            elif isinstance(src_data, (str, int, bool)):
                if src_data != dst_data:
                    result = False
                    return result

        elif checkType == 'contain':
            if isinstance(src_data, dict):
                for key in src_data.keys():
                    if key in dst_data.keys() and result:
                        check_json(src_data[key], dst_data[key], checkType='contain')
                    else:
                        result = False
                        return result
            elif isinstance(src_data, list):
                for src, dst in zip(sorted(src_data), sorted(dst_data)):
                    if result:
                        check_json(src, dst, checkType='contain')
                    else:
                        return result
            elif isinstance(src_data, (str, int, bool)):
                if src_data != dst_data:
                    result = False
                    return result

        elif checkType == 'gte':
            try:
                if isinstance(src_data, str):
                    src_data = int(src_data)
                if isinstance(dst_data, str):
                    dst_data = int(dst_data)
            except (ValueError, TypeError):
                pass
            if isinstance(src_data, int) and isinstance(dst_data, int):
                result = src_data >= dst_data
            else:
                result = False

        elif checkType == 'lte':
            try:
                if isinstance(src_data, str):
                    src_data = int(src_data)
                if isinstance(dst_data, str):
                    dst_data = int(dst_data)
            except (ValueError, TypeError):
                pass
            if isinstance(src_data, int) and isinstance(dst_data, int):
                result = src_data <= dst_data
            else:
                result = False

        elif checkType == 'notNull':
            if dst_data is not None and src_data == 'true':
                result = True
            elif dst_data is None and src_data == 'false':
                result = True
            elif dst_data is not None:
                result = True
            else:
                result = False
        else:
            result = False
        return result
    except Exception as E:
        logger.info(f'check_json error: {E}')
        return False


def get_json(jsonData: dict, checkRule: str):
    """Extract a value from a JSON dict using a dotted path.

    Supports:
        - ``"data.token"`` → nested dict access
        - ``".data.token"`` → leading dot (legacy compat)
        - ``"data.list.0.id"`` → array index access

    Args:
        jsonData: Parsed JSON dict.
        checkRule: Dotted path, e.g. ``"data.total"``.

    Returns:
        The extracted value, or an error string on failure.
    """
    try:
        rulelist = checkRule.split('.')
        if rulelist and rulelist[0] == '':
            rulelist.pop(0)
        for key in rulelist:
            try:
                key = int(key)
            except (ValueError, TypeError):
                pass
            try:
                jsonData = jsonData[key]
            except (KeyError, IndexError):
                return f'response cant find key {key}'
    except Exception:
        pass
    return jsonData


def get_step_ref_regex():
    """Return the compiled step-reference regex patterns used by
    ``resolve_step_refs`` and ``resolve_step_refs_in_string``."""
    return _STEP_REF_RE, _SUB_STEP_REF_RE
