# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json as _json
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class CaseItem(BaseModel):
    """单个测试用例的结构化输出"""
    case_id: str = Field(description="测试用例ID")
    api_name: str = Field(description="API接口名称")
    api_address: str = Field(description="API接口地址")
    request_type: str = Field(description="请求方法（GET/POST/PUT/DELETE）")
    http_code: str = Field(description="期望HTTP状态码")
    examine_type: str = Field(default="Regular_check", description="断言类型")

    @field_validator("case_id", mode="before")
    @classmethod
    def _coerce_case_id(cls, v):
        return str(v) if v is not None else ""


class CaseList(BaseModel):
    """用例生成的结构化输出 — case_generate 节点的输出格式"""
    all_cases: List[CaseItem] = Field(description="生成的所有测试用例列表")


class FailCase(BaseModel):
    """失败用例的结构化输出 — tolerates model deviations in field naming."""
    name: str = Field(default="", description="测试用例名称")
    case_id: str = Field(default="", description="失败的测试用例ID")
    status: str = Field(default="失败", description="执行结果")
    detail: str = Field(default="", description="失败原因")

    @field_validator("case_id", mode="before")
    @classmethod
    def _coerce_case_id(cls, v):
        return str(v) if v is not None else ""

    @field_validator("name", mode="before")
    @classmethod
    def _default_name(cls, v):
        return v if v else ""

    @model_validator(mode="before")
    @classmethod
    def _remap_fields(cls, data):
        """Map non-standard field names that the LLM might produce."""
        if isinstance(data, dict):
            # fail_reason → detail
            if "fail_reason" in data and not data.get("detail"):
                data["detail"] = data.pop("fail_reason")
            # error → detail
            if "error" in data and not data.get("detail"):
                data["detail"] = data.pop("error")
            # reason → detail
            if "reason" in data and not data.get("detail"):
                data["detail"] = data.pop("reason")
            # auto-generate name from case_id
            if not data.get("name") and data.get("case_id"):
                data["name"] = f"用例 {data['case_id']}"
        return data


class CaseRunDetails(BaseModel):
    """用例执行结果的结构化输出 — case_run 节点的输出格式"""
    run_fail_cases: List[FailCase] = Field(
        default_factory=list,
        description="执行失败的用例列表（空列表表示全部通过）"
    )
    total_count: int = Field(default=0, description="总执行用例数")
    pass_count: int = Field(default=0, description="通过用例数")
    fail_count: int = Field(default=0, description="失败用例数")

    @model_validator(mode="before")
    @classmethod
    def _remap_fail_list(cls, data):
        """Handle LLM returning a single dict or list of non-standard objects."""
        if isinstance(data, dict):
            fails = data.get("run_fail_cases")
            if fails is None:
                # Try alternate field names
                fails = data.get("fail_cases") or data.get("failed_cases") or data.get("failures") or []
                data["run_fail_cases"] = fails
            if isinstance(fails, dict):
                data["run_fail_cases"] = [fails]
            if isinstance(fails, list):
                data["run_fail_cases"] = [
                    f if isinstance(f, dict) else {"detail": str(f)} for f in fails
                ]
        return data


# ═══════════════════════════════════════════════════════════════════════
# Scenario (multi-API flow) output models
# ═══════════════════════════════════════════════════════════════════════

class ScenarioStepResult(BaseModel):
    """Result of executing a single scenario step."""
    step_order: int = Field(description="Step number in the scenario")
    api_name: str = Field(description="API name")
    case_id: str = Field(description="The test case ID that was executed")
    success: bool = Field(description="Whether this step passed")
    http_status: str = Field(default="", description="HTTP status code returned")
    response_preview: str = Field(default="", description="Truncated response for debugging")
    error_detail: str = Field(default="", description="Error message if failed")

    @field_validator("case_id", "http_status", "response_preview", "error_detail", mode="before")
    @classmethod
    def coerce_to_str(cls, v: object) -> str:
        """Coerce int/float/dict/None to str."""
        if v is None:
            return ""
        if isinstance(v, dict):
            return _json.dumps(v, ensure_ascii=False)
        return str(v)


class ScenarioRunResult(BaseModel):
    """Structured output for the scenario_run node."""
    scenario_name: str = Field(description="Name of the executed scenario")
    total_steps: int = Field(description="Total number of steps")
    passed_steps: int = Field(description="Number of passed steps")
    failed_steps: int = Field(description="Number of failed steps")
    step_results: List[ScenarioStepResult] = Field(
        default_factory=list,
        description="Detailed results for each step"
    )
    data_flow_chain: list = Field(
        default_factory=list,
        description="Trace of what data was passed between steps (free-form, can be strings or dicts)"
    )

    @field_validator("data_flow_chain", mode="before")
    @classmethod
    def coerce_data_flow_chain(cls, v):
        """Wrap a single dict/string into a list — the LLM often outputs
        a single object instead of an array."""
        if isinstance(v, dict):
            return [v]
        if isinstance(v, str):
            return [{"description": v}]
        return v
