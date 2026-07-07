# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


from langgraph.graph import MessagesState
from pydantic import BaseModel, Field, field_validator
from typing import Annotated, List, Dict, Any, Literal, Type



class Ai_test_State(MessagesState):
    """State for the agent system, extends MessagesState with next field."""

    # Runtime Variables
    locale: str = "en-US"
    selected_apis: list = []        # APIs selected in the select_apis node
    available_apis: list = []       # All APIs available in the project (from backend query)
    _api_list_ready: bool = False   # 断点恢复标识：True = 已查询过接口列表，跳过查询直接走 interrupt
    interrupt_message: str = ""     # Message to show user during interrupt
    case_group_id: int = 0          # Dynamically created test case group ID
    all_case_generate: list[str] = []
    fail_case: list = []
    update_case: list = []
    final_report: str = ""
    update_count: int = 0
    is_new_task: Annotated[bool, lambda current, update: update]  # track last-message state

    # ── Scenario mode fields ───────────────────────────────────────────
    intent_type: str = "test_case_generation"   # "test_case_generation" | "scenario_test_generation"
    scenario_plan: dict = {}                    # ScenarioPlan from LLM (serialised dict)
    _scenario_plan_ready: bool = False          # Interrupt-resume guard for scenario_design
    scenario_steps: list = []                   # Confirmed ScenarioStep list (dicts)
    scenario_case_ids: list = []                # Generated case IDs in step order
    scenario_results: dict = {}                 # ScenarioRunResult from execution
    scenario_report_text: str = ""              # Final scenario report markdown
    scenario_update_count: int = 0              # Fix-and-rerun iterations for scenario

class StartTestInput(BaseModel):
    ids: List[int] = Field(description="具体的测试用例ID列表，用于指定执行哪些测试用例。")



class ApiInput(BaseModel):
    """添加API接口数据模型"""
    name: Annotated[str, Field(description="API的名称，用于标识该接口")]
    api_address: Annotated[str, Field(description="API的地址（URL）")]
    case_name: Annotated[str, Field(description="测试用例组名称，如'AI生成-用户登录'。同名组自动复用，接口用例将添加到该组下")]
    http_type: Annotated[str, Field(default="HTTP", description="HTTP协议类型，如HTTP、HTTPS")] = "HTTP"
    request_type: Annotated[str, Field(default="POST", description="HTTP请求方法，如GET、POST、PUT、DELETE等")] = "POST"
    head_dict: Annotated[
        List[Dict[str, Any]], Field(
            default=[],
            description="请求头列表，每个元素包含 name(header名)、value(header值) 和 interrelate(bool，统一设为 false) 字段。"
                        "value 支持动态语法：$N.字段路径 引用前置步骤响应（如 $1.data.token），$var.变量名 引用全局变量。"
                        "无需设置 interrelate=true，系统根据 $ 前缀自动识别引用类型"
        )] = []
    request_parameter_type: Annotated[str, Field(default="raw", description="请求参数类型，如raw、form-data等")] = "raw"
    format_raw: Annotated[bool, Field(default=False, description="是否格式化原始数据")] = False
    request_list: Annotated[str, Field(
        default="{}",
        description="请求体内容，JSON字符串。参数值支持动态语法：$N.字段路径 引用前置步骤响应（如 $1.data.token），"
                    "$var.变量名 引用全局变量（如 $var.reg_username）。无需设置 interrelate=true"
    )] = "{}"
    examine_type: Annotated[str, Field(
        default="Regular_check",
        description="断言类型：Regular_check(正则匹配) / json(JSON字段校验) / entirely_check(完全匹配) / no_check(不校验)。"
                    "重要：如果此API的响应数据会被后续步骤通过 $N.field 步骤引用，必须设为 'json' 并填写 json_check_data，"
                    "让 checkRule 定义好所有可供后续步骤引用的字段路径"
    )]
    regular_param: Annotated[str, Field(default=None, description="正则表达式参数名字")]
    http_code: Annotated[str, Field(default="200", description="期望的HTTP状态码")] = "200"
    response_data: Annotated[str, Field(default="", description="期望的响应数据（用于断言）")] = ""
    json_check_data: Annotated[
        List[Dict[str, str]], Field(
            default=[],
            description="JSON校验规则列表。每项包含：name(字段名), value(期望值), "
                        "checkType(gte/lte/equal/contain/notNull), checkRule(JSON路径如 data.data.token)。"
                        "当 examine_type='json' 时必填，至少需要一条记录（如 notNull 检查关键字段）"
        )] = []

class UpdateApiInput(BaseModel):
    """修改API接口数据模型"""
    name: Annotated[str, Field(description="API的名称，用于标识该接口")]
    case_id: Annotated[str, Field(description="API的case id，用于标识该接口")]
    api_address: Annotated[str, Field(description="API的地址（URL）")]
    http_type: Annotated[str, Field(default="HTTP", description="HTTP协议类型，如HTTP、HTTPS")] = "HTTP"
    request_type: Annotated[str, Field(default="POST", description="HTTP请求方法，如GET、POST、PUT、DELETE等")] = "POST"
    head_dict: Annotated[
        List[Dict[str, Any]], Field(
            default=[],
            description="请求头列表，每个元素包含 name(header名)、value(header值) 和 interrelate(bool，统一设为 false) 字段。"
                        "value 支持动态语法：$N.字段路径 引用前置步骤响应（如 $1.data.token），$var.变量名 引用全局变量。"
                        "无需设置 interrelate=true，系统根据 $ 前缀自动识别引用类型"
        )] = []
    request_parameter_type: Annotated[str, Field(default="raw", description="请求参数类型，如raw、form-data等")] = "raw"
    format_raw: Annotated[bool, Field(default=False, description="是否格式化原始数据")] = False
    request_list: Annotated[str, Field(
        default="{}",
        description="请求体内容，JSON字符串。参数值支持动态语法：$N.字段路径 引用前置步骤响应（如 $1.data.token），"
                    "$var.变量名 引用全局变量（如 $var.reg_username）。无需设置 interrelate=true"
    )] = "{}"
    examine_type: Annotated[str, Field(
        default="Regular_check",
        description="断言类型：Regular_check(正则匹配) / json(JSON字段校验) / entirely_check(完全匹配) / no_check(不校验)。"
                    "重要：如果此API的响应数据会被后续步骤通过 $N.field 步骤引用，必须设为 'json' 并填写 json_check_data，"
                    "让 checkRule 定义好所有可供后续步骤引用的字段路径"
    )]
    regular_param: Annotated[str, Field(default=None, description="正则表达式参数名字")]
    http_code: Annotated[str, Field(default="200", description="期望的HTTP状态码")] = "200"
    response_data: Annotated[str, Field(default="", description="期望的响应数据（用于断言）")] = ""
    json_check_data: Annotated[
        List[Dict[str, str]], Field(
            default=[],
            description="JSON校验规则列表。每项包含：name(字段名), value(期望值), "
                        "checkType(gte/lte/equal/contain/notNull), checkRule(JSON路径如 data.data.token)。"
                        "当 examine_type='json' 时必填，至少需要一条记录"
        )] = []


# ═══════════════════════════════════════════════════════════════════════
# Scenario (multi-API flow) models
# ═══════════════════════════════════════════════════════════════════════

class ScenarioDependency(BaseModel):
    """A single data dependency: this step's request field ← source step's response."""
    target_field: str = Field(
        description="The field path in this API's request that needs data, "
                    "e.g. 'head_dict.Authorization' or 'request_list.data.token'"
    )
    source_step: int = Field(
        description="The 1-indexed step number that provides the data"
    )
    source_api_id: str = Field(
        description="The source API's api_id (from selected_apis, used as placeholder "
                    "until the actual AutomationCaseApi.id is returned)"
    )
    source_json_path: str = Field(
        description="JSONPath to extract from the source response, e.g. '.data.token'"
    )
    description: str = Field(
        default="", description="Human-readable description of this dependency"
    )

    @field_validator("source_api_id", mode="before")
    @classmethod
    def coerce_source_api_id(cls, v: object) -> str:
        """Coerce int to str — the LLM may return integer API IDs from the backend."""
        return str(v)


class ScenarioStep(BaseModel):
    """A single step in the business scenario flow."""
    step_order: int = Field(description="Step number (1-indexed), defines execution order")
    api_id: str = Field(description="The API's api_id from selected_apis")
    api_name: str = Field(description="The API's name")
    description: str = Field(description="What this step does in the business flow")
    depends_on: List[int] = Field(
        default_factory=list,
        description="List of step_order values this step depends on for data"
    )
    dependencies: List[ScenarioDependency] = Field(
        default_factory=list,
        description="Specific data dependencies from prior step responses"
    )

    @field_validator("api_id", mode="before")
    @classmethod
    def coerce_api_id(cls, v: object) -> str:
        """Coerce int to str — the LLM may return integer API IDs from the backend."""
        return str(v)


class ScenarioPlan(BaseModel):
    """Complete scenario design produced by the LLM."""
    scenario_name: str = Field(
        description="Name of this business scenario, e.g. '用户注册登录流程'"
    )
    scenario_description: str = Field(
        description="Description of the end-to-end business flow"
    )
    steps: List[ScenarioStep] = Field(
        description="Ordered steps in the scenario (1-indexed step_order)"
    )