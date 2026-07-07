"""
Shared OpenAPI schema utilities for drf-spectacular.

Provides reusable parameter definitions, response wrappers, and helpers
so that every APIView can declare request/response schemas consistently
without duplicating common definitions.
"""

from rest_framework import serializers
from drf_spectacular.utils import (
    OpenApiParameter, OpenApiResponse, OpenApiExample,
)
from drf_spectacular.types import OpenApiTypes


# ---------------------------------------------------------------------------
# Common query / path parameters (used by many views)
# ---------------------------------------------------------------------------

PROJECT_ID_PARAM = OpenApiParameter(
    "project_id", str, description="项目 ID", required=True,
)

PROJECT_ID_OPTIONAL = OpenApiParameter(
    "project_id", str, description="项目 ID", required=False,
)

API_ID_PARAM = OpenApiParameter(
    "api_id", str, description="接口 ID", required=True,
)

CASE_ID_PARAM = OpenApiParameter(
    "case_id", str, description="用例 ID", required=True,
)

PAGE_PARAM = OpenApiParameter(
    "page", int, description="页码", required=False,
)

PAGE_SIZE_PARAM = OpenApiParameter(
    "page_size", int, description="每页条数", required=False,
)

NAME_PARAM = OpenApiParameter(
    "name", str, description="名称（模糊搜索）", required=False,
)

FIRST_GROUP_ID_PARAM = OpenApiParameter(
    "first_group_id", str, description="一级分组 ID", required=False,
)

API_GROUP_FIRST_ID_PARAM = OpenApiParameter(
    "apiGroupLevelFirst_id", str, description="一级分组 ID", required=False,
)

TASK_NAME_PARAM = OpenApiParameter(
    "taskName", str, description="任务名称", required=False,
)

TIME_PARAM = OpenApiParameter(
    "time", str, description="测试时间", required=True,
)


# ---------------------------------------------------------------------------
# Standard response serializers (real Serializer classes — created once)
# Using real classes avoids the "identical names" warning from inline_serializer.
# ---------------------------------------------------------------------------

class _StdResponseSerializer(serializers.Serializer):
    """Standard {code, msg, data} — data is JSON (any type)."""
    code = serializers.CharField()
    msg = serializers.CharField()
    data = serializers.JSONField()


class _StdResponseNoDataSerializer(serializers.Serializer):
    """Standard {code, msg} — no data field."""
    code = serializers.CharField()
    msg = serializers.CharField()


class _PaginatedDataSerializer(serializers.Serializer):
    """Paginated inner: {data: [...], page: int, total: int}."""
    data = serializers.ListField()
    page = serializers.IntegerField()
    total = serializers.IntegerField()


class _PaginatedResponseSerializer(serializers.Serializer):
    """Paginated full: {code, msg, data: {data, page, total}}."""
    code = serializers.CharField()
    msg = serializers.CharField()
    data = _PaginatedDataSerializer()


class _ErrorResponseSerializer(serializers.Serializer):
    """Error: {code, msg, data: null}."""
    code = serializers.CharField()
    msg = serializers.CharField()
    data = serializers.JSONField(required=False, allow_null=True)


class _AuthErrorSerializer(serializers.Serializer):
    """Auth error: {detail: str}."""
    detail = serializers.CharField()


# Singleton instances — reused by every view, no duplicate warnings
RESP_DATA_ANY = _StdResponseSerializer()
RESP_NO_DATA = _StdResponseNoDataSerializer()
RESP_PAGINATED = _PaginatedResponseSerializer()
RESP_ERROR = _ErrorResponseSerializer()
RESP_AUTH_ERROR = _AuthErrorSerializer()


# ---------------------------------------------------------------------------
# Response helpers (all now pass response= serializer to generate schema)
# ---------------------------------------------------------------------------

def success_response(description="成功", data_example=None):
    """
    Standard 200 response with {code, msg, data} wrapper.
    Both schema AND example are provided for Swagger.
    """
    value = {
        "code": "999999",
        "msg": "成功",
        "data": data_example if data_example is not None else {},
    }
    return OpenApiResponse(
        description=description,
        response=RESP_DATA_ANY,
        examples=[OpenApiExample("Success", value=value)],
    )


def list_response(description="成功", item_example=None):
    """Standard paginated list response with proper schema."""
    value = {
        "code": "999999",
        "msg": "成功",
        "data": {
            "data": [item_example] if item_example else [],
            "page": 1,
            "total": 1,
        },
    }
    return OpenApiResponse(
        description=description,
        response=RESP_PAGINATED,
        examples=[OpenApiExample("Success", value=value)],
    )


def create_response(description="创建成功", id_field="id", id_value=1):
    """Response for a create operation that returns an ID, with proper schema."""
    return OpenApiResponse(
        description=description,
        response=RESP_DATA_ANY,
        examples=[
            OpenApiExample(
                "Success",
                value={
                    "code": "999999",
                    "msg": "成功",
                    "data": {id_field: id_value},
                },
            )
        ],
    )


def simple_response(description="成功"):
    """Response with no data payload (just code + msg), with proper schema."""
    return OpenApiResponse(
        description=description,
        response=RESP_NO_DATA,
        examples=[
            OpenApiExample(
                "Success",
                value={"code": "999999", "msg": "成功"},
            )
        ],
    )


def error_responses():
    """Common 400/401 error responses with proper schemas."""
    return {
        400: OpenApiResponse(
            description="请求参数错误",
            response=RESP_ERROR,
            examples=[
                OpenApiExample(
                    "ParamError",
                    value={"code": "999996", "msg": "参数有误!", "data": None},
                )
            ],
        ),
        401: OpenApiResponse(
            description="未认证",
            response=RESP_AUTH_ERROR,
            examples=[
                OpenApiExample(
                    "Unauthorized",
                    value={"detail": "身份认证信息未提供。"},
                )
            ],
        ),
    }


def param_error_response():
    """Shortcut for 400 parameter error."""
    return OpenApiResponse(
        description="请求参数错误",
        response=RESP_ERROR,
        examples=[
            OpenApiExample(
                "ParamError",
                value={"code": "999996", "msg": "参数有误!", "data": None},
            )
        ],
    )


def not_found_response(description="资源不存在"):
    """404-style not-found response (returned as 200 with error code)."""
    return OpenApiResponse(
        description=description,
        response=RESP_ERROR,
        examples=[
            OpenApiExample(
                "NotFound",
                value={"code": "999995", "msg": "项目不存在!", "data": None},
            )
        ],
    )


def permission_denied_response():
    """403-style permission denied (returned as 200 with error code)."""
    return OpenApiResponse(
        description="无操作权限",
        response=RESP_ERROR,
        examples=[
            OpenApiExample(
                "Forbidden",
                value={"code": "999983", "msg": "无操作权限！", "data": None},
            )
        ],
    )


# ---------------------------------------------------------------------------
# Request body builder helper
# ---------------------------------------------------------------------------

def json_body(properties, required=None, description="请求参数"):
    """
    Build a standard JSON request body schema dict.

    Args:
        properties: dict of {name: {type, description, ...}} or
                    list of (name, type, description, **kwargs) tuples.
        required: list of required field names.
        description: body description.
    """
    if isinstance(properties, list):
        props = {}
        for item in properties:
            name = item[0]
            props[name] = {
                "type": item[1],
                "description": item[2],
            }
            if len(item) > 3:
                props[name].update(item[3])
    else:
        props = properties

    return {
        "application/json": {
            "type": "object",
            "required": required or list(props.keys()),
            "properties": props,
            "description": description,
        }
    }
