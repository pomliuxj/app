import logging
import json
import yaml
import requests
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from api_test.common.common import record_dynamic
from api_test.models import Project, ApiInfo, ApiGroupLevelFirst, ApiParameter, ApiParameterRaw, ApiResponse, ApiOperationHistory
from django.db import transaction

from api_test.serializers import ApiInfoDeserializer, ApiHeadDeserializer, ApiParameterDeserializer, \
    ApiResponseDeserializer

logger = logging.getLogger(__name__)  # 这里使用 __name__ 动态搜索定义的 logger 配置，这里有一个层次关系的知识点。


# HTTP method names (lowercase), used to distinguish from path-item metadata keys
_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}


def _is_openapi3(data):
    """Detect if the schema is OpenAPI 3.x (vs Swagger 2.0)."""
    return "openapi" in data and data.get("openapi", "").startswith("3.")


def _get_schemas(data):
    """Get schema definitions, compatible with both Swagger 2.0 and OpenAPI 3.0."""
    if _is_openapi3(data):
        return (data.get("components") or {}).get("schemas") or {}
    return data.get("definitions") or {}


def _get_content_type(operation):
    """
    Determine request content type from an operation object.
    Compatible with Swagger 2.0 ``consumes`` and OpenAPI 3.0 ``requestBody``.
    Returns (content_type_string_or_None, parameter_type_string).
    """
    # Swagger 2.0 style
    consumes = operation.get("consumes", [])
    if consumes:
        content_type = consumes[0]
        if content_type == "application/json":
            return content_type, "raw"
        else:
            return content_type, "form-data"

    # OpenAPI 3.0 style — look in requestBody
    rb = operation.get("requestBody")
    if rb and "content" in rb:
        for ct in rb["content"]:
            if ct == "application/json":
                return ct, "raw"
            return ct, "form-data"

    # Default to form-data for methods without a body (e.g. GET with query params).
    # Properly-specified Swagger/OpenAPI docs will have consumes / requestBody for
    # methods that actually carry a JSON body, so they won't hit this fallback.
    return None, "form-data"


def _get_parameters(operation, path_item=None):
    """
    Collect operation-level parameters, optionally merged with path-level parameters.
    OpenAPI 3.0 allows ``parameters`` on the path item itself.
    Returns a list of parameter dicts.
    """
    params = list(operation.get("parameters", []))
    if path_item:
        # Path-level parameters apply to all operations on this path
        path_params = path_item.get("parameters", [])
        if path_params:
            # Avoid duplicates: path params typically defined once; merge if not already present
            param_names = {p.get("name") for p in params}
            for pp in path_params:
                if pp.get("name") not in param_names:
                    params.append(pp)
    return params


def _normalise_type(raw_type: str) -> str:
    """Map a raw type name to one of the ApiResponse choices: 'Int' or 'String'."""
    if not raw_type:
        return "String"
    t = raw_type.lower()
    if t in ("int", "integer", "number", "float", "double"):
        return "Int"
    return "String"


def _extract_response_fields(data_obj, tier=""):
    """
    Recursively extract response fields from a JSON-like dict, preserving hierarchy.

    :param data_obj: dict-like object to extract from
    :param tier: parent path string, e.g. "data" or "data.user"
    :return: list of field dicts with name, value, _type, tier, required, description
    """
    fields = []
    if not isinstance(data_obj, dict):
        return fields

    for key, val in data_obj.items():
        _val_type = _normalise_type(type(val).__name__)
        _current_tier = f"{tier}.{key}" if tier else key

        if isinstance(val, dict):
            fields.append({
                "name": key, "value": "",
                "_type": "String", "tier": tier,
                "required": False, "description": "",
            })
            fields.extend(_extract_response_fields(val, _current_tier))
        elif isinstance(val, list) and val and isinstance(val[0], dict):
            fields.append({
                "name": key, "value": "",
                "_type": "String", "tier": tier,
                "required": False, "description": "",
            })
            fields.extend(_extract_response_fields(val[0], _current_tier))
        else:
            fields.append({
                "name": key,
                "value": str(val),
                "_type": _val_type,
                "tier": tier,
                "required": False,
                "description": "",
            })
    return fields


def _resolve_schema_ref(ref_str, schemas):
    """Resolve a ``$ref`` or ``#/definitions/Foo`` or ``#/components/schemas/Foo`` string."""
    if not ref_str or not isinstance(ref_str, str):
        return None
    # Handle both Swagger 2.0 (#/definitions/Xxx) and OpenAPI 3.0 (#/components/schemas/Xxx)
    parts = ref_str.lstrip("#/").split("/")
    name = parts[-1] if parts else ""
    return schemas.get(name) or {}


def swagger_api(url, project, user, apiGroupLevelFirst_id):
    """
    请求swagger地址，数据解析
    兼容 Swagger 2.0 和 OpenAPI 3.0 格式
    :param url: swagger地址
    :param project: 项目ID
    :param user: 用户model
    :param apiGroupLevelFirst_id : 分组id
    :return:
    """
    try:
        headers = {"Accept": "application/json"}
        req = requests.get(url, timeout=10, headers=headers)
        req.raise_for_status()  # 检查 HTTP 状态码，非 2xx 抛异常
    except requests.exceptions.ConnectionError as E:
        logger.error(f'导入链接连接失败：{url} - {E}')
        raise Exception(f'无法连接到 Swagger 地址: {url}')
    except requests.exceptions.Timeout as E:
        logger.error(f'导入链接超时：{url} - {E}')
        raise Exception(f'请求 Swagger 地址超时: {url}')
    except requests.exceptions.HTTPError as E:
        logger.error(f'导入链接 HTTP 错误：{url} - {E}')
        raise Exception(f'Swagger 地址返回错误 (HTTP {req.status_code}): {url}')
    except requests.exceptions.RequestException as E:
        logger.error(f'导入链接请求失败：{url} - {E}')
        raise Exception(f'请求 Swagger 地址失败: {url}')

    try:
        schema_data = req.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        # JSON 解析失败时尝试 YAML（drf-spectacular 默认返回 YAML）
        try:
            schema_data = yaml.safe_load(req.text)
            if not isinstance(schema_data, dict):
                raise ValueError("解析结果不是有效的字典")
        except (yaml.YAMLError, ValueError):
            logger.error(f'导入链接 JSON/YAML 解析均失败：{url} - 响应内容: {req.text[:500]}')
            raise Exception(f'Swagger 地址返回的不是有效的 OpenAPI/Swagger 文档格式（JSON/YAML）')

    if "paths" not in schema_data:
        raise Exception('JSON 中未找到 paths 字段，请确认该地址是有效的 Swagger/OpenAPI 文档')

    schemas = _get_schemas(schema_data)
    apis = schema_data["paths"]

    for api_path, path_item in apis.items():
        # path_item may be None (empty path object) — skip it
        if not path_item:
            continue

        for method, operation in path_item.items():
            # Skip non-HTTP-method keys (OpenAPI 3.0 path-level fields: parameters, summary, etc.)
            if method.lower() not in _HTTP_METHODS:
                continue

            # Fresh requestApi per method to avoid state leaking between methods on the same path
            requestApi = {
                "project_id": project, "status": True, "mockStatus": False, "mockCode": "", "desc": "",
                "httpType": "HTTP", "responseList": [], "apiGroupLevelFirst_id": apiGroupLevelFirst_id,
                "headDict": [],
                "apiAddress": api_path,
                "requestType": method.upper(),
                "name": operation.get("summary", "") or operation.get("operationId", "") or api_path,
                "description": operation.get("description", "") or "",
            }

            # Determine content type and parameter type
            content_type, param_type = _get_content_type(operation)
            requestApi["requestParameterType"] = param_type
            if content_type:
                requestApi["headDict"] = [{"name": "Content-Type", "value": content_type}]

            # Merge path-level + operation-level parameters
            all_params = _get_parameters(operation, path_item)

            for param in all_params:
                param_in = param.get("in", "")
                if param_in == "header":
                    requestApi["headDict"].append({
                        "name": param.get("name", "").title(),
                        "value": "String",
                    })
                elif param_in == "body":
                    # Swagger 2.0 body parameter — resolve via schema $ref or inline schema
                    body_schema = param.get("schema", {})
                    if not body_schema:
                        # Older Swagger 2.0: body param has "name" used as DTO name
                        dto = param.get("name", "")
                        dto = dto[:1].upper() + dto[1:] if dto else ""
                        body_schema = schemas.get(dto, {})

                    _extract_body_params(requestApi, body_schema, schemas)

                elif param_in == "query":
                    _extract_query_params(requestApi, operation, all_params)

            # OpenAPI 3.0 requestBody — extract body parameters (only if not already set)
            if param_type == "raw" and not requestApi.get("requestList"):
                rb = operation.get("requestBody", {})
                rb_content = rb.get("content", {})
                json_content = rb_content.get("application/json", {})
                rb_schema = json_content.get("schema", {})
                if rb_schema:
                    _extract_body_params(requestApi, rb_schema, schemas)

            # ── Parse response schemas ───────────────────────────────
            _responses = operation.get("responses", {})
            _response_fields = []
            _http_code = ""

            for status_code, resp_obj in _responses.items():
                if not status_code.startswith("2"):
                    continue
                _http_code = status_code

                # OpenAPI 3.0: content → application/json → schema
                # Swagger 2.0: schema at top level
                content = resp_obj.get("content", {})
                json_content = content.get("application/json", {})
                schema = json_content.get("schema", resp_obj.get("schema", {}))

                # ── Strategy: examples first (real structure), schema as fallback ──
                examples = json_content.get("examples", {})
                _used_examples = False

                for _ex_name, _ex_obj in examples.items():
                    _ex_value = _ex_obj.get("value", {}) if isinstance(_ex_obj, dict) else {}
                    if not isinstance(_ex_value, dict) or not _ex_value:
                        continue
                    # Recursively extract with tier hierarchy
                    _response_fields = _extract_response_fields(_ex_value)
                    _used_examples = True
                    break  # Only use first example

                # ── Fallback: extract from schema properties ──────────
                if not _used_examples and schema:
                    ref = schema.get("$ref", "")
                    if ref:
                        schema = _resolve_schema_ref(ref, schemas) or schema
                    properties = schema.get("properties", {})
                    required_fields = schema.get("required", [])
                    for key, prop in properties.items():
                        _response_fields.append({
                            "name": key,
                            "value": str(prop.get("example", "")),
                            "_type": _normalise_type(prop.get("type", "string")),
                            "tier": "",
                            "required": key in required_fields,
                            "description": prop.get("description", ""),
                        })

                break  # Only parse the first 2xx response

            requestApi["responseList"] = _response_fields
            if _http_code:
                requestApi["mockCode"] = _http_code
            logger.info(
                "Parsed %d response fields (http_code=%s) for %s %s",
                len(_response_fields), _http_code, method.upper(), api_path,
            )

            requestApi["userUpdate"] = user.id
            add_swagger_api(requestApi, user)


def _extract_body_params(requestApi, body_schema, schemas):
    """
    Extract body parameters from a JSON schema and set requestApi["requestList"].
    Handles both inline schemas and $ref references.
    """
    # Resolve $ref
    ref = body_schema.get("$ref", "")
    if ref:
        body_schema = _resolve_schema_ref(ref, schemas) or body_schema

    properties = body_schema.get("properties", {})
    if not properties:
        return

    if requestApi.get("requestParameterType") == "raw":
        parameter = {}
        for key, value in properties.items():
            # OpenAPI 3.0: type may be inside "schema" or at top level; handle both
            prop_type = _normalise_type(value.get("type", "string"))
            parameter[key] = prop_type
        requestApi["requestList"] = json.dumps(parameter, ensure_ascii=False)
    else:
        parameter = []
        required_list = body_schema.get("required", [])
        for key, value in properties.items():
            # OpenAPI 3.0: type may be inside "schema" or at top level
            prop_type = _normalise_type(value.get("type", "string"))
            parameter.append({
                "name": key,
                "value": prop_type,
                "_type": prop_type,
                "required": key in required_list,
                "restrict": "",
                "description": value.get("description", ""),
            })
        requestApi["requestList"] = parameter


def _extract_query_params(requestApi, operation, all_params):
    """
    Extract query parameters and set requestApi["requestList"].
    """
    try:
        if requestApi.get("requestParameterType") == "raw":
            parameter = {}
            for param in all_params:
                if param.get("in") == "query":
                    parameter[param["name"]] = {
                        "描述": param.get("description", ""),
                        "是否必传": str(param.get("required", False)),
                    }
            if parameter:
                requestApi["requestList"] = json.dumps(parameter, ensure_ascii=False)
        else:
            parameter = []
            for param in all_params:
                if param.get("in") == "query":
                    # OpenAPI 3.0: type is nested inside schema; Swagger 2.0: type at top level
                    _schema = param.get("schema", {})
                    raw_type = param.get("type") or (_schema.get("type") if _schema else "string")
                    _type = _normalise_type(raw_type)
                    parameter.append({
                        "name": param["name"],
                        "value": _type,
                        "_type": _type,
                        "required": param.get("required", False),
                        "restrict": "",
                        "description": param.get("description", ""),
                    })
            requestApi["requestList"] = parameter
    except Exception as E:
        logger.error("_extract_query_params error: %s", E, exc_info=True)


def add_swagger_api(data, user):
    """
    swagger接口写入数据库
    :param data:  json数据
    :param user:  用户model
    :return:
    """
    try:
        logger.info(json.dumps(data))
        obj = Project.objects.get(id=data["project_id"])
        obi = ApiGroupLevelFirst.objects.get(id=data["apiGroupLevelFirst_id"], project=data["project_id"])
        try:
            with transaction.atomic():  # 执行错误后，帮助事物回滚
                serialize = ApiInfoDeserializer(data=data)
                if serialize.is_valid():
                    serialize.save(project=obj,apiGroupLevelFirst=obi)
                    api_id = serialize.data.get("id")
                    if len(data.get("headDict")):
                        for i in data["headDict"]:
                            if i.get("name"):
                                i["api"] = api_id
                                head_serialize = ApiHeadDeserializer(data=i)
                                if head_serialize.is_valid():
                                    head_serialize.save(api=ApiInfo.objects.get(id=api_id))
                    if data["requestParameterType"] == "form-data":
                        if data.get("requestList"):
                            for i in data["requestList"]:
                                if i.get("name"):
                                    i["api"] = api_id
                                    param_serialize = ApiParameterDeserializer(data=i)
                                    if param_serialize.is_valid():
                                        param_serialize.save(api=ApiInfo.objects.get(id=api_id))
                                    else:
                                        logger.warning(
                                            "Parameter '%s' invalid (API %s): %s",
                                            i.get("name", ""), api_id, param_serialize.errors,
                                        )
                    else:
                        if data.get("requestList"):
                            raw_data = data["requestList"]
                            if isinstance(raw_data, str):
                                # 尝试规范化：旧代码可能写入 Python dict 字符串（单引号）
                                if not raw_data.strip().startswith("{"):
                                    raw_data = "{}"
                                else:
                                    try:
                                        json.loads(raw_data)
                                    except json.JSONDecodeError:
                                        # 可能是 Python str(dict) 格式，尝试修复
                                        try:
                                            fixed = raw_data.replace("'", "\"")
                                            json.loads(fixed)
                                            raw_data = fixed
                                        except json.JSONDecodeError:
                                            raw_data = "{}"
                            elif isinstance(raw_data, (dict, list)):
                                raw_data = json.dumps(raw_data, ensure_ascii=False)
                            else:
                                raw_data = "{}"
                            ApiParameterRaw(api=ApiInfo.objects.get(id=api_id), data=raw_data).save()
                    if data.get("responseList"):
                        logger.info(
                            "Saving %d response fields for API '%s'",
                            len(data["responseList"]), data.get("name", ""),
                        )
                        for i in data["responseList"]:
                            if i.get("name"):
                                i["api"] = api_id
                                response_serialize = ApiResponseDeserializer(data=i)
                                if response_serialize.is_valid():
                                    response_serialize.save(api=ApiInfo.objects.get(id=api_id))
                                else:
                                    logger.warning(
                                        "Response field '%s' invalid: %s",
                                        i.get("name", ""), response_serialize.errors,
                                    )
                    else:
                        logger.info("No responseList for API '%s'", data.get("name", ""))
                    record_dynamic(project=data["project_id"],
                                   _type="新增", operationObject="接口", user=user.pk,
                                   data="新增接口“%s”" % data["name"])
                    api_record = ApiOperationHistory(api=ApiInfo.objects.get(id=api_id),
                                                     user=User.objects.get(id=user.pk),
                                                     description="新增接口“%s”" % data["name"])
                    api_record.save()
        except Exception as e:
            logger.exception(e)
            return False
    except ObjectDoesNotExist:
        return False
