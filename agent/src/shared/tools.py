import json
import os
import logging
import asyncio
import threading
from typing import List, Dict, Any, Literal, Type
from dotenv import load_dotenv

import requests
from pydantic import BaseModel, Field
from langchain.tools import BaseTool

from src.framework.state import StartTestInput, ApiInput, UpdateApiInput

logger = logging.getLogger(__name__)
load_dotenv(override=True)

# ---------------------------------------------------------------------------
# Configuration — sourced from environment variables with sensible defaults
# ---------------------------------------------------------------------------
AUTOMATION_BASE_URL = os.getenv("AUTOMATION_BASE_URL", "http://127.0.0.1:8000")
AUTOMATION_AUTH_TOKEN = os.getenv("AUTOMATION_AUTH_TOKEN", "2810f46e2bdfe3d0ea853d54d2ce03c72b85af87")
AUTOMATION_PROJECT_ID = int(os.getenv("AUTOMATION_PROJECT_ID", "1"))
AUTOMATION_CASE_ID = int(os.getenv("AUTOMATION_CASE_ID", "19"))
AUTOMATION_HOST_ID = int(os.getenv("AUTOMATION_HOST_ID", "1"))
RECURSION_LIMIT = int(os.getenv("RECURSION_LIMIT", "100"))

# Runtime state — set once when the test case group is created, then shared
# across all tools so the LLM never needs to pass case_group_id manually.
_runtime_case_group_id: int = 0

# Per-name locks to prevent concurrent creation of duplicate case groups / groups
_lock_dict: Dict[str, threading.Lock] = {}
_lock_dict_lock = threading.Lock()


def _get_lock(name: str) -> threading.Lock:
    """Get or create a threading.Lock for the given name (thread-safe)."""
    with _lock_dict_lock:
        if name not in _lock_dict:
            _lock_dict[name] = threading.Lock()
        return _lock_dict[name]


def set_runtime_case_group_id(case_group_id: int):
    global _runtime_case_group_id
    _runtime_case_group_id = case_group_id
    logger.info("Runtime case_group_id set to %d", case_group_id)


def get_runtime_case_group_id() -> int:
    return _runtime_case_group_id or AUTOMATION_CASE_ID


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _get_auth_headers() -> Dict[str, str]:
    """Return common authorization headers for backend requests."""
    return {
        "Authorization": f"Token {AUTOMATION_AUTH_TOKEN}",
        "Content-Type": "application/json",
    }


def _handle_request_error(e: requests.exceptions.RequestException) -> Dict[str, Any]:
    """Normalize a Requests exception into a JSON-safe error dict."""
    error_msg = str(e)
    status_code = getattr(e.response, "status_code", None)
    logger.error("Backend request failed: %s (status=%s)", error_msg, status_code)
    return {"error": error_msg, "status_code": status_code}


def _build_api_payload(
    name: str,
    api_address: str,
    automation_case_id: int,
    http_type: str = "HTTP",
    request_type: str = "POST",
    head_dict: List[Dict[str, Any]] = None,
    request_parameter_type: str = "raw",
    format_raw: bool = False,
    request_list: str = "{}",
    examine_type: str = "Regular_check",
    regular_param: str = None,
    http_code: str = "200",
    response_data: str = "",
    json_check_data: List[Dict[str, str]] = None,
    extra_fields: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Build the common API payload shared by AddApiTool and UpdateApiTool."""

    # ── Convert request_list to the format expected by the backend ──
    # For form-data: backend expects a list of {name, value, interrelate} dicts
    # For raw:      backend expects a JSON string
    if request_parameter_type == "form-data" and isinstance(request_list, str):
        try:
            _parsed = json.loads(request_list)
            if isinstance(_parsed, list):
                request_list = _parsed
        except (json.JSONDecodeError, TypeError):
            pass  # Keep as string if parsing fails

    payload = {
        "project_id": AUTOMATION_PROJECT_ID,
        "automationTestCase_id": automation_case_id,
        "name": name,
        "httpType": http_type,
        "requestType": request_type,
        "apiAddress": api_address,
        "headDict": head_dict or [],
        "requestParameterType": request_parameter_type,
        "formatRaw": format_raw,
        "requestList": request_list,
        "examineType": examine_type,
        "RegularParam": regular_param,
        "httpCode": http_code,
        "responseData": response_data,
        "jsonCheckData": [
            {
                "name": item.get("name", ""),
                "value": item.get("value", ""),
                "checkType": item.get("checkType", "notNull"),
                "checkRule": item.get("checkRule", ""),
            }
            for item in (json_check_data or [])
        ],
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload


# ---------------------------------------------------------------------------
# Pydantic models for tool args_schema
# ---------------------------------------------------------------------------
class JsonCheckItem(BaseModel):
    """JSON断言数据模型"""
    name: str = Field(..., description="字段名")
    value: str = Field(..., description="期望值")
    checkType: Literal["gte", "lte", "equal", "contain", "notNull"] = Field(
        ...,
        description="检查类型：gte(大于), lte(小于), equal(等于), contain(包含), notNull(不为空)",
    )
    checkRule: str = Field(..., description="检查规则，用于自定义校验规则data.data.username")


class SearchApiInfoInput(BaseModel):
    """查询API详情的数据模型"""
    case_id: str = Field(..., description="接口用例的ID（api_id）")


class ApiDocInfoInput(BaseModel):
    """查询接口文档详情的数据模型"""
    api_id: str = Field(..., description="接口ID")


class ListProjectApisInput(BaseModel):
    """查询项目下所有API列表的数据模型"""
    project_id: str = Field(..., description="项目ID")


class CreateTestCaseInput(BaseModel):
    """创建自动化测试用例组（容器）的数据模型"""
    case_name: str = Field(..., description="用例组名称，如'AI生成-用户登录测试'。用例组是接口用例的容器，创建后会返回 case_id，后续添加接口用例时需要传入")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
class StartAutomationTestTool(BaseTool):
    """启动自动化测试的工具，按顺序执行所有用例，支持 $N.field 步骤引用。"""

    name: str = "start_automation_test"
    description: str = (
        "启动一个自动化测试任务，按顺序逐个执行所有用例（支持 $N.field 步骤间参数引用）。"
        "需要提供具体测试用例 ID 列表，会按传入顺序依次执行，前一步的响应可供后续步骤通过 $N.field 引用。\n"
        "返回格式：{\"code\":\"999999\",\"data\":{\"result\":[{\"success\":true/false,\"case_id\":1}]}}\n"
        "- success=false 表示该用例执行失败"
    )
    args_schema: Type[BaseModel] = StartTestInput

    def _run(self, ids: List[int]) -> Dict[str, Any]:
        """同步执行工具逻辑 — 使用 start_test_sequential 支持步骤间数据关联"""
        url = f"{AUTOMATION_BASE_URL}/api/automation/start_test_sequential"
        payload = {
            "project_id": AUTOMATION_PROJECT_ID,
            "case_id": get_runtime_case_group_id(),
            "host_id": AUTOMATION_HOST_ID,
            "id": ids,
        }
        try:
            response = requests.post(url, json=payload, headers=_get_auth_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return _handle_request_error(e)

    async def _arun(self, ids: List[int]) -> Dict[str, Any]:
        """异步执行 — 使用 asyncio.to_thread 桥接同步实现"""
        return await asyncio.to_thread(self._run, ids)


class AddApiTool(BaseTool):
    """向用例组中添加接口测试用例的工具（自动创建/复用用例组）。"""

    name: str = "add_automation_api"
    description: str = (
        "添加一个接口测试用例。传入 case_name 指定用例组名称，工具会自动查找已有同名用例组"
        "（存在则复用 case_id，不存在则新建），然后将接口用例添加到该组下。\n"
        "返回格式：{\"code\":\"999999\",\"msg\":\"成功！\",\"data\":{\"api_id\":123},\"case_group_id\":5}\n"
        "- code=\"999999\" 表示创建成功\n"
        "- api_id 是新增接口用例的 ID，用于后续执行和修复\n"
        "- case_group_id 是用例组 ID\n"
        "\n参数值统一使用 $ 前缀引用动态值（无需 interrelate 标志）：\n"
        "- `$N.字段路径` — 引用第 N 步的响应数据，如 \"$1.data.token\"\n"
        "- `$变量名` — 引用全局变量，如 \"$reg_username\"\n"
        "\n系统按 $ 后首字符自动区分：数字 = 步骤引用，非数字 = 全局变量。"
    )
    args_schema: Type[BaseModel] = ApiInput

    # ── Case group helpers (inline so LLM doesn't need a separate tool) ──

    def _find_existing_case(self, case_name: str, headers: Dict[str, str]):
        """返回同名用例组的 case_id，不存在则返回 None。"""
        url = (
            f"{AUTOMATION_BASE_URL}/api/automation/case_list"
            f"?project_id={AUTOMATION_PROJECT_ID}&name={case_name}"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json().get("data", {}).get("data", [])
            if data:
                return data[0]["id"]
        except requests.exceptions.RequestException:
            pass
        return None

    def _ensure_group(self, headers: Dict[str, str]) -> int:
        """返回一个已有的分组 id，没有则创建默认分组（并发安全）。"""
        group_name = "AI自动生成"
        lock = _get_lock(f"__group__{group_name}")
        with lock:
            # Double-check: another thread may have created it while we waited
            list_url = f"{AUTOMATION_BASE_URL}/api/automation/group?project_id={AUTOMATION_PROJECT_ID}"
            try:
                resp = requests.get(list_url, headers=headers, timeout=30)
                resp.raise_for_status()
                groups = resp.json().get("data", [])
                if groups:
                    return groups[0]["id"]
            except requests.exceptions.RequestException:
                pass
            # Still not found — create it under the lock
            create_url = f"{AUTOMATION_BASE_URL}/api/automation/add_group"
            payload = {"project_id": AUTOMATION_PROJECT_ID, "name": group_name}
            try:
                resp = requests.post(create_url, json=payload, headers=headers, timeout=30)
                resp.raise_for_status()
                group_id = resp.json().get("data", {}).get("group_id")
                logger.info("Created group '%s' id=%s", group_name, group_id)
                return group_id
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"无法获取或创建用例分组: {e}")

    def _resolve_case_id(self, case_name: str, headers: Dict[str, str]) -> int:
        """获取或创建用例组，返回 case_id（并发安全）。

        使用 per-name 锁 + 双重检查，避免并发场景下创建出多个同名用例组。
        如果后端返回"已存在"，回退到查询已有 case_id（处理跨进程/锁失效的极端情况）。
        """
        # Fast path: check without lock first
        case_id = self._find_existing_case(case_name, headers)
        if case_id is not None:
            logger.info("Reusing existing case group '%s' id=%s", case_name, case_id)
            return case_id

        # Slow path: acquire lock and double-check before creating
        lock = _get_lock(case_name)
        with lock:
            # Double-check: another thread may have created it while we waited
            case_id = self._find_existing_case(case_name, headers)
            if case_id is not None:
                logger.info(
                    "Case group '%s' created by another thread, reusing id=%s",
                    case_name, case_id,
                )
                return case_id

            group_id = self._ensure_group(headers)
            url = f"{AUTOMATION_BASE_URL}/api/automation/add_case"
            payload = {
                "project_id": AUTOMATION_PROJECT_ID,
                "caseName": case_name,
                "automationGroupLevelFirst_id": group_id,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            # 后端并发保护：如果返回"存在相同名称"，回退到查询
            if body.get("code") == "999997":
                logger.warning(
                    "Backend reported duplicate for '%s', looking up existing...",
                    case_name,
                )
                case_id = self._find_existing_case(case_name, headers)
                if case_id is not None:
                    return case_id
                raise RuntimeError(f"用例组'{case_name}'已存在但查询不到，可能数据不一致")
            case_id = body.get("data", {}).get("case_id")
            if not case_id:
                raise RuntimeError(f"创建用例组'{case_name}'失败: {body.get('msg', '未知错误')}")
            logger.info("Created case group '%s' id=%s", case_name, case_id)
            return case_id

    # ── Main tool logic ─────────────────────────────────────────────────

    def _run(
        self,
        name: str,
        api_address: str,
        case_name: str,
        http_type: str = "HTTP",
        request_type: str = "POST",
        head_dict: List[Dict[str, Any]] = None,
        request_parameter_type: str = "raw",
        format_raw: bool = False,
        request_list: str = "{}",
        examine_type: str = "Regular_check",
        regular_param: str = None,
        http_code: str = "200",
        response_data: str = "",
        json_check_data: List[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """同步：解析用例组 → 添加接口用例"""
        headers = {
            "accept": "*/*",
            "authorization": f"Token {AUTOMATION_AUTH_TOKEN}",
            "Content-Type": "application/json",
        }
        try:
            automation_case_id = self._resolve_case_id(case_name, headers)
        except Exception as e:
            return {"error": str(e)}

        url = f"{AUTOMATION_BASE_URL}/api/automation/add_new_api"
        payload = _build_api_payload(
            name=name,
            api_address=api_address,
            automation_case_id=automation_case_id,
            http_type=http_type,
            request_type=request_type,
            head_dict=head_dict,
            request_parameter_type=request_parameter_type,
            format_raw=format_raw,
            request_list=request_list,
            examine_type=examine_type,
            regular_param=regular_param,
            http_code=http_code,
            response_data=response_data,
            json_check_data=json_check_data,
        )
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict) and result.get("code") == "999999":
                result["case_group_id"] = automation_case_id
            return result
        except requests.exceptions.RequestException as e:
            return _handle_request_error(e)

    async def _arun(
        self,
        name: str,
        api_address: str,
        case_name: str,
        http_type: str = "HTTP",
        request_type: str = "POST",
        head_dict: List[Dict[str, Any]] = None,
        request_parameter_type: str = "raw",
        format_raw: bool = False,
        request_list: str = "{}",
        examine_type: str = "Regular_check",
        regular_param: str = None,
        http_code: str = "200",
        response_data: str = "",
        json_check_data: List[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """异步"""
        return await asyncio.to_thread(
            self._run,
            name=name,
            api_address=api_address,
            case_name=case_name,
            http_type=http_type,
            request_type=request_type,
            head_dict=head_dict,
            request_parameter_type=request_parameter_type,
            format_raw=format_raw,
            request_list=request_list,
            examine_type=examine_type,
            regular_param=regular_param,
            http_code=http_code,
            response_data=response_data,
            json_check_data=json_check_data,
        )


class UpdateApiTool(BaseTool):
    """修改API接口的工具，调用后端 API 更新接口配置。"""

    name: str = "update_automation_api"
    description: str = (
        "修改接口测试用例的配置参数。必须传入 Search_Api_Info 返回的所有字段，只修改需要修复的部分。\n"
        "返回格式：{\"code\":\"999999\",\"msg\":\"成功！\"}\n"
        "- code=\"999999\" 表示修改成功\n"
        "- code=\"999996\" 表示参数有误，检查 http_code 是否为合法值（200/400/404/500/502/302）"
    )
    args_schema: Type[BaseModel] = UpdateApiInput

    def _run(
        self,
        name: str,
        case_id: str,
        api_address: str,
        http_type: str = "HTTP",
        request_type: str = "POST",
        head_dict: List[Dict[str, Any]] = None,
        request_parameter_type: str = "raw",
        format_raw: bool = False,
        request_list: str = "{}",
        examine_type: str = "Regular_check",
        regular_param: str = None,
        http_code: str = "200",
        response_data: str = "",
        json_check_data: List[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """同步更新 API 测试用例"""
        url = f"{AUTOMATION_BASE_URL}/api/automation/update_api"
        headers = {
            "accept": "*/*",
            "authorization": f"Token {AUTOMATION_AUTH_TOKEN}",
            "Content-Type": "application/json",
        }

        payload = _build_api_payload(
            name=name,
            api_address=api_address,
            automation_case_id=get_runtime_case_group_id(),
            http_type=http_type,
            request_type=request_type,
            head_dict=head_dict,
            request_parameter_type=request_parameter_type,
            format_raw=format_raw,
            request_list=request_list,
            examine_type=examine_type,
            regular_param=regular_param,
            http_code=http_code,
            response_data=response_data,
            json_check_data=json_check_data,
            extra_fields={"id": case_id},
        )
        logger.info("修改 api 接口接口数据为:%s", json.dumps(payload, ensure_ascii=False))

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return _handle_request_error(e)

    async def _arun(
        self,
        name: str,
        case_id: str,
        api_address: str,
        http_type: str = "HTTP",
        request_type: str = "POST",
        head_dict: List[Dict[str, Any]] = None,
        request_parameter_type: str = "raw",
        format_raw: bool = False,
        request_list: str = "{}",
        examine_type: str = "Regular_check",
        regular_param: str = None,
        http_code: str = "200",
        response_data: str = "",
        json_check_data: List[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """异步更新 API 测试用例"""
        return await asyncio.to_thread(
            self._run,
            name=name,
            case_id=case_id,
            api_address=api_address,
            http_type=http_type,
            request_type=request_type,
            head_dict=head_dict,
            request_parameter_type=request_parameter_type,
            format_raw=format_raw,
            request_list=request_list,
            examine_type=examine_type,
            regular_param=regular_param,
            http_code=http_code,
            response_data=response_data,
            json_check_data=json_check_data,
        )


class SearchApiInfoTool(BaseTool):
    """查询测试用例详情的工具"""

    name: str = "Search_Api_Info"
    description: str = (
        "查询接口用例的完整配置信息。\n"
        "返回格式：{\"code\":\"999999\",\"data\":{\"id\":117,\"name\":\"登录_正常\",\"httpType\":\"HTTP\","
        "\"requestType\":\"POST\",\"apiAddress\":\"/api/user/login\",\"header\":[...],"
        "\"requestParameterType\":\"raw\",\"parameterRaw\":{\"data\":\"{...}\"},"
        "\"examineType\":\"Regular_check\",\"httpCode\":\"200\",\"responseData\":\"\"}}\n"
        "- httpCode 是断言的期望状态码\n"
        "- parameterRaw.data 是请求体 JSON 字符串\n"
        "- header 是请求头列表"
    )
    args_schema: Type[BaseModel] = SearchApiInfoInput

    def _run(self, case_id: str) -> Dict[str, Any]:
        """同步查询 API 详情"""
        url = (
            f"{AUTOMATION_BASE_URL}/api/automation/api_info"
            f"?project_id={AUTOMATION_PROJECT_ID}&case_id={get_runtime_case_group_id()}&api_id={case_id}"
        )
        try:
            response = requests.get(url, headers=_get_auth_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return _handle_request_error(e)

    async def _arun(self, case_id: str) -> Dict[str, Any]:
        """异步查询 API 详情"""
        return await asyncio.to_thread(self._run, case_id)


class ApiDocInfoTool(BaseTool):
    """查询接口文档详情的工具，获取接口的完整信息（请求参数、请求头、响应等）。"""

    name: str = "api_doc_info"
    description: str = "查询接口文档的详细信息，返回接口的请求参数、请求头、响应格式等完整信息。"
    args_schema: Type[BaseModel] = ApiDocInfoInput

    def _run(self, api_id: str) -> Dict[str, Any]:
        """同步查询接口文档详情"""
        url = (
            f"{AUTOMATION_BASE_URL}/api/api/api_info"
            f"?project_id={AUTOMATION_PROJECT_ID}&api_id={api_id}"
        )
        try:
            response = requests.get(url, headers=_get_auth_headers())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return _handle_request_error(e)

    async def _arun(self, api_id: str) -> Dict[str, Any]:
        """异步查询接口文档详情"""
        return await asyncio.to_thread(self._run, api_id)


class ListProjectApisTool(BaseTool):
    """查询项目下所有API接口列表的工具，用于 select_apis 节点获取可选的接口。"""

    name: str = "list_project_apis"
    description: str = "查询当前项目下已有的所有API接口列表，用于提供给用户选择哪些接口需要生成测试用例。"
    args_schema: Type[BaseModel] = ListProjectApisInput

    def _run(self, project_id: str) -> Dict[str, Any]:
        """同步查询项目API列表"""
        url = (
            f"{AUTOMATION_BASE_URL}/api/api/api_list"
            f"?project_id={project_id}"
        )
        logger.info("Querying project APIs at %s", url)
        try:
            response = requests.get(url, headers=_get_auth_headers(), timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to query project APIs at %s: %s", url, e)
            return _handle_request_error(e)

    async def _arun(self, project_id: str) -> Dict[str, Any]:
        """异步查询项目API列表"""
        return await asyncio.to_thread(self._run, project_id)


# ---------------------------------------------------------------------------
# Scenario (multi-API flow) tools
# ---------------------------------------------------------------------------

class CreateGlobalVariableInput(BaseModel):
    """创建/更新全局变量的输入"""
    variablesName: str = Field(
        ..., description="变量名称（英文），如 'reg_username', 'reg_email'。"
                         "引用时使用 $变量名 格式"
    )
    Code: str = Field(
        ..., description="Python 代码，print 输出的值即为变量值。"
                         "例如: print('test_user_123') 或 "
                         "print('user_' + str(__import__('random').randint(1000, 9999)))"
    )


class ListGlobalVariablesInput(BaseModel):
    """查询全局变量列表的输入"""
    variablesName: str = Field(
        default="", description="变量名模糊搜索（可选），留空则返回所有"
    )


class CreateGlobalVariableTool(BaseTool):
    """创建或更新全局变量的工具。

    全局变量用于在接口参数中引用动态值，引用格式为 $变量名。
    典型场景：注册接口的用户名、邮箱、手机号等需要每次不同的参数，
    使用全局变量生成随机值，然后在接口请求参数中通过 $变量名 引用。
    """

    name: str = "create_global_variable"
    description: str = (
        "创建或更新一个全局变量。变量创建后可在接口参数中通过 $变量名 引用。\n"
        "Code 字段填写 Python 代码，使用 print() 输出变量值。\n"
        "典型用法：\n"
        "- 动态用户名: Code=\"print('user_'+str(__import__('random').randint(1000,9999)))\"\n"
        "- 固定值: Code=\"print('test_value_123')\"\n"
        "- 时间戳: Code=\"import time; print(str(int(time.time())))\"\n"
        "返回格式：{\"code\":\"999999\",\"msg\":\"成功\"} 表示创建/更新成功\n"
        "- 如果同名变量已存在，会自动更新为新的 Code"
    )
    args_schema: Type[BaseModel] = CreateGlobalVariableInput

    def _run(self, variablesName: str, Code: str) -> Dict[str, Any]:
        """同步：创建或更新全局变量（使用 DELETE 端点做 upsert）"""
        url = f"{AUTOMATION_BASE_URL}/api/global/global_variables"
        payload = {
            "project_id": AUTOMATION_PROJECT_ID,
            "variablesName": variablesName,
            "Code": Code,
        }
        logger.info("Creating/updating global variable '%s'", variablesName)
        try:
            response = requests.delete(
                url, json=payload, headers=_get_auth_headers(), timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            logger.info("Global variable '%s' result: %s", variablesName, result)
            return result
        except requests.exceptions.RequestException as e:
            return _handle_request_error(e)

    async def _arun(self, variablesName: str, Code: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._run, variablesName, Code)


class ListGlobalVariablesTool(BaseTool):
    """查询项目中已有的全局变量列表。"""

    name: str = "list_global_variables"
    description: str = (
        "查询项目中已有的全局变量列表，用于避免创建重复变量名。\n"
        "返回格式：{\"code\":\"999999\",\"data\":{\"data\":[{\"id\":1,\"variablesName\":\"xxx\",\"Code\":\"...\"}]}}"
    )
    args_schema: Type[BaseModel] = ListGlobalVariablesInput

    def _run(self, variablesName: str = "") -> Dict[str, Any]:
        """同步查询全局变量列表"""
        url = f"{AUTOMATION_BASE_URL}/api/global/global_variables?page_size=100"
        if variablesName:
            url += f"&variablesName={variablesName}"
        try:
            response = requests.get(url, headers=_get_auth_headers(), timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return _handle_request_error(e)

    async def _arun(self, variablesName: str = "") -> Dict[str, Any]:
        return await asyncio.to_thread(self._run, variablesName)


class ExecuteScenarioStepInput(BaseModel):
    """单步骤场景测试执行输入"""
    case_id: str = Field(..., description="要执行的测试用例ID（单个）")
    host_id: str = Field(default="", description="目标Host ID，默认使用系统配置")
    project_id: str = Field(default="", description="项目ID，默认使用系统配置")


class ExecuteScenarioStepTool(BaseTool):
    """顺序执行单个场景步骤的测试工具。

    每次调用只执行一个测试用例，并返回包含响应数据的详细结果。
    执行结果会自动保存到后端数据库，后续步骤可以通过 $N.field
    语法引用前一步的响应数据（如 $1.data.token）。

    重要：此工具每次只能执行一个 case_id，多个步骤需要多次调用，
    并等待每次调用完成后再调用下一个。
    """

    name: str = "execute_scenario_step"
    description: str = (
        "顺序执行业务场景中的一个步骤（单个API测试用例）。\n"
        "每次调用执行一个用例，返回执行结果和响应数据。\n"
        "执行结果会自动保存到后端，后续用例可通过 $N.field 语法引用（如 $1.data.token）。\n"
        "返回格式：{\"code\":\"999999\",\"data\":{\"result\":[{\"success\":true/false,"
        "\"case_id\":1,\"response_code\":200,\"response_data\":\"...\"}]}}\n"
        "- success=true 表示该步骤执行成功\n"
        "- response_data 是接口返回的实际响应数据（JSON字符串）\n"
        "- 必须按步骤顺序逐个调用，每次只传一个 case_id"
    )
    args_schema: Type[BaseModel] = ExecuteScenarioStepInput

    def _run(self, case_id: str, host_id: str = "", project_id: str = "") -> Dict[str, Any]:
        """同步执行单个测试步骤 — 调用顺序执行接口"""
        url = f"{AUTOMATION_BASE_URL}/api/automation/start_test_sequential"
        payload = {
            "project_id": int(project_id) if project_id else AUTOMATION_PROJECT_ID,
            "case_id": get_runtime_case_group_id(),
            "host_id": int(host_id) if host_id else AUTOMATION_HOST_ID,
            "id": [int(case_id)],
        }
        logger.info(
            "Executing scenario step case_id=%s via %s", case_id, url,
        )
        try:
            response = requests.post(url, json=payload, headers=_get_auth_headers(), timeout=120)
            response.raise_for_status()
            result = response.json()
            logger.info("Scenario step %s result: %s", case_id, str(result)[:200])
            return result
        except requests.exceptions.RequestException as e:
            return _handle_request_error(e)

    async def _arun(self, case_id: str, host_id: str = "", project_id: str = "") -> Dict[str, Any]:
        """异步执行单个测试步骤"""
        return await asyncio.to_thread(self._run, case_id, host_id, project_id)

# ── Module-level tool instances (shared singletons) ─────────────────────
start_test_tool = StartAutomationTestTool()
add_test_tool = AddApiTool()
update_test_tool = UpdateApiTool()
search_tool = SearchApiInfoTool()
api_doc_tool = ApiDocInfoTool()
list_apis_tool = ListProjectApisTool()
execute_step_tool = ExecuteScenarioStepTool()
create_global_var_tool = CreateGlobalVariableTool()
list_global_vars_tool = ListGlobalVariablesTool()
